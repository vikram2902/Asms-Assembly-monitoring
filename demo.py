import socket
import threading
import time
from gpiozero import Button
from datetime import datetime
import logging

# ------------------------
# Logging Setup
# ------------------------
logging.basicConfig(
    filename="job_pass_log.txt",
    format='%(message)s',
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
TRIGGER1_PIN = 17  # GPIO17
TRIGGER2_PIN = 27  # GPIO27

# ------------------------
# State Variables
# ------------------------
latest_result = None
current_job = 1
connected_sock = None
trigger_received = threading.Event()
trigger1_detected = threading.Event()
trigger2_detected = threading.Event()
cycle_start = None
operator_name = ""
job_in_progress = False

# ------------------------
# Command Builders
# ------------------------
def build_command(job_number: int) -> bytes:
    return b'\x02' + f"set job {job_number}".encode('ascii') + b'\x03'

def build_trigger_command() -> bytes:
    return b'\x02trigger\x03'

# ------------------------
# Result Listener Thread
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
# Trigger Handlers
# ------------------------
def on_trigger1():
    global job_in_progress
    if not job_in_progress:
        print(f" Sensor 1 (GPIO17) pulse detected at {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
        trigger1_detected.set()
        check_dual_trigger()
    else:
        print(" Ignored trigger from Sensor 1 — job already in progress")

def on_trigger2():
    global job_in_progress
    if not job_in_progress:
        print(f" Sensor 2 (GPIO27) pulse detected at {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
        trigger2_detected.set()
        check_dual_trigger()
    else:
        print("Ignored trigger from Sensor 2 — job already in progress")

def check_dual_trigger():
    if trigger1_detected.is_set() and trigger2_detected.is_set():
        print(" Both sensors triggered — proceeding to job")
        trigger_received.set()

# ------------------------
# Job Execution with Retry
# ------------------------
def run_job(job_number):
    global latest_result, connected_sock

    start_time = time.time()
    attempt = 0

    while True:
        attempt += 1
        try:
            connected_sock.sendall(build_command(job_number))
            print(f"[Job] Switching to job {job_number}")
            _ = connected_sock.recv(1024)

            time.sleep(0.2)

            connected_sock.sendall(build_trigger_command())
            print(f"[Trigger] Trigger sent for job {job_number} (Attempt {attempt})")

            wait_start = time.time()
            timeout =0.2  # wait max 0.2s each attempt

            while time.time() - wait_start < timeout:
                if latest_result:
                    result = latest_result
                    latest_result = None
                    if "true" in result:
                        job_time = time.time() - start_time
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        log_line = f"{timestamp}    Job {job_number} completed by {operator_name} in {job_time:.2f}s with {attempt - 1} retries"
                        print(f" {log_line}")
                        logger.info(log_line)
                        return
                    elif "false" in result:
                        print(f" Job {job_number} failed (Attempt {attempt}) — retrying...")
                        break  # retry
                    else:
                        print(f" Unknown result: {result}")
                        break
                time.sleep(0.05)

        except Exception as e:
            print(f"[Error] During job {job_number}: {e}")
            return

# ------------------------
# Main Execution
# ------------------------
def main():
    global connected_sock, current_job, cycle_start, operator_name, job_in_progress

    try:
        operator_name = input("Enter operator name: ").strip()
        print(f"[System] Operator: {operator_name}")
        logger.info(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}    --- New session started by {operator_name} ---")

        print(f"[Startup] Connecting to {CAMERA_IP}:{COMMAND_PORT} ...")
        connected_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        connected_sock.connect((CAMERA_IP, COMMAND_PORT))

        threading.Thread(target=result_listener, daemon=True).start()

        # Setup triggers
        trigger1 = Button(TRIGGER1_PIN, pull_up=False)
        trigger2 = Button(TRIGGER2_PIN, pull_up=False)
        trigger1.when_pressed = on_trigger1
        trigger2.when_pressed = on_trigger2

        print("\n[Ready] Waiting for BOTH GPIO triggers...")
        cycle_start = time.time()

        while True:
            trigger_received.wait()
            trigger_received.clear()
            job_in_progress = True

            run_job(current_job)

            job_in_progress = False
            trigger1_detected.clear()
            trigger2_detected.clear()

            if current_job % 3 == 0:
                cycle_time = time.time() - cycle_start
                msg = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}    Cycle of 3 jobs completed by {operator_name} in {cycle_time:.2f} seconds"
                print(f"\n[Cycle ✅] {msg}\n")
                logger.info(msg)
                cycle_start = time.time()

            print(f"[System] Job {current_job} complete. Waiting for BOTH triggers again...")
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

