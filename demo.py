import socket
import threading
import time
from gpiozero import Button
from signal import pause
from datetime import datetime
import logging

# ------------------------
# Logging Setup
# ------------------------
logging.basicConfig(
    filename="job_pass_log.txt",
    format='%(asctime)s %(message)s',
    filemode='a'
)
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ------------------------
# Configuration
# ------------------------
CAMERA_IP = '192.168.0.1'
COMMAND_PORT = 2300
RESULT_PORT = 2300
TRIGGER_PIN = 17  # BCM pin 17 (physical pin 11)

# ------------------------
# State variables
# ------------------------
latest_result = None
current_job = 1
connected_sock = None
trigger_received = threading.Event()
cycle_start = None
operator_name = ""

# ------------------------
# Build job and trigger commands
# ------------------------
def build_command(job_number: int) -> bytes:
    return b'\x02' + f"set job {job_number}".encode('ascii') + b'\x03'

def build_trigger_command() -> bytes:
    return b'\x02trigger\x03'

# ------------------------
# Thread: Listen for result from camera
# ------------------------
def result_listener():
    global latest_result
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as result_sock:
            result_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            result_sock.connect((CAMERA_IP, RESULT_PORT))
            print(f"[Startup] Connected to result port {RESULT_PORT}")

            while True:
                data = result_sock.recv(1024)
                if data:
                    latest_result = data.decode(errors='ignore').strip().lower()
    except Exception as e:
        print(f"[Result Thread] Error: {e}")

# ------------------------
# Trigger callback: set event
# ------------------------
def on_trigger():
    print("\n[Trigger] GPIO pulse detected")
    trigger_received.set()

# ------------------------
# Log successful jobs
# ------------------------
def log_passed_job(job_number, operator_name):
    logger.info(f"Job {job_number} passed by operator {operator_name}")

# ------------------------
# Handle job execution
# ------------------------
def run_job(job_number):
    global latest_result, connected_sock

    try:
        # Send job switch
        job_command = build_command(job_number)
        connected_sock.sendall(job_command)
        print(f"[Job] Switching to job {job_number}")
        _ = connected_sock.recv(1024)

        time.sleep(0.2)

        # Send trigger
        connected_sock.sendall(build_trigger_command())
        print("[Trigger] Trigger command sent")

        # Wait for result
        while True:
            if latest_result:
                result = latest_result
                latest_result = None

                if "true" in result:
                    print(f"[✅] Job {job_number} passed")
                    log_passed_job(job_number, operator_name)
                    return True
                elif "false" in result:
                    print(f"[❌] Job {job_number} failed — retrying...")
                    return False
                else:
                    print(f"[⚠️] Unknown result: {result}")
                    return False
            time.sleep(0.05)
    except Exception as e:
        print(f"[Error] During job {job_number}: {e}")
        return False

# ------------------------
# Main Loop
# ------------------------
def main():
    global connected_sock, current_job, cycle_start, operator_name

    try:
        operator_name = input("Enter operator name: ").strip()
        print(f"[System] Operator: {operator_name}")

        print(f"[Startup] Connecting to {CAMERA_IP}:{COMMAND_PORT} ...")
        connected_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        connected_sock.connect((CAMERA_IP, COMMAND_PORT))

        # Start result listener thread
        threading.Thread(target=result_listener, daemon=True).start()

        # GPIO setup
        trigger = Button(TRIGGER_PIN, pull_up=False)
        trigger.when_pressed = on_trigger

        print("\n[Ready] Waiting for GPIO trigger...")
        print(f"[System] Starting from job {current_job}")

        cycle_start = time.time()

        while True:
            trigger_received.wait()
            trigger_received.clear()

            passed = False
            while not passed:
                passed = run_job(current_job)

            if current_job % 3 == 0:
                cycle_end = time.time()
                cycle_time = cycle_end - cycle_start

                print(f"\n[Cycle ✅] Operator {operator_name} completed a cycle in {cycle_time:.2f} seconds\n")
                logger.info(f"Cycle completed by operator {operator_name} in {cycle_time:.2f} seconds")

                cycle_start = time.time()

            print(f"[System] Job {current_job} complete. Waiting for next trigger...")
            trigger_received.wait()
            trigger_received.clear()
            current_job += 1

    except KeyboardInterrupt:
        print("\n[System] Exiting gracefully by Ctrl+C")
    except Exception as e:
        print(f"[Startup Error] {e}")
    finally:
        if connected_sock:
            connected_sock.close()
        print("[System] Socket closed. Bye!")

# ------------------------
# Start Program
# ------------------------
if __name__ == "__main__":
    main()

