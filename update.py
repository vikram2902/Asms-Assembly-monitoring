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
job_in_progress = False

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
# Trigger callback
# ------------------------
def on_trigger():
    global job_in_progress
    if not job_in_progress:
        print(f"\n[🔔] GPIO pulse detected at {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
        trigger_received.set()
    else:
        print("[⚠️] Ignored trigger — job already in progress")

# ------------------------
# Handle job execution with retries and timing
# ------------------------
def run_job(job_number):
    global latest_result, connected_sock

    start_time = time.time()
    attempt = 0

    while True:
        attempt += 1
        try:
            job_command = build_command(job_number)
            connected_sock.sendall(job_command)
            print(f"[Job] Switching to job {job_number}")
            _ = connected_sock.recv(1024)

            time.sleep(0.2)

            connected_sock.sendall(build_trigger_command())
            print(f"[Trigger] Trigger sent for job {job_number} (Attempt {attempt})")

            timeout = 5  # seconds
            wait_start = time.time()

            while time.time() - wait_start < timeout:
                if latest_result:
                    result = latest_result
                    latest_result = None
                    if "true" in result:
                        job_time = time.time() - start_time
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        log_line = f"{timestamp}    Job {job_number} completed by {operator_name} in {job_time:.2f}s with {attempt - 1} retries"
                        print(log_line)
                        logger.info(log_line)
                        return
                    elif "false" in result:
                        print(f"[❌] Job {job_number} failed (Attempt {attempt}) — retrying...")
                        break
                    else:
                        print(f"[⚠️] Unknown result: {result}")
                        break
                time.sleep(0.05)

            if time.time() - start_time > 20:
                print("[Error] Job timeout exceeded — aborting")
                return

        except Exception as e:
            print(f"[Error] During job {job_number}: {e}")
            return

# ------------------------
# Main Loop
# ------------------------
def main():
    global connected_sock, current_job, cycle_start, operator_name, job_in_progress

    try:
        operator_name = input("Enter operator name: ").strip()
        print(f"[System] Operator: {operator_name}")
        session_line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}    --- New session started by operator: {operator_name} ---"
        logger.info(session_line)

        print(f"[Startup] Connecting to {CAMERA_IP}:{COMMAND_PORT} ...")
        connected_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        connected_sock.connect((CAMERA_IP, COMMAND_PORT))

        threading.Thread(target=result_listener, daemon=True).start()

        trigger = Button(TRIGGER_PIN, pull_up=False)
        trigger.when_pressed = on_trigger

        print("\n[Ready] Waiting for GPIO trigger...")
        print(f"[System] Starting from job {current_job}")
        cycle_start = time.time()

        while True:
            trigger_received.wait()
            trigger_received.clear()

            job_in_progress = True
            run_job(current_job)
            job_in_progress = False

            if current_job % 3 == 0:
                cycle_end = time.time()
                cycle_time = cycle_end - cycle_start
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                log_line = f"{timestamp}    Cycle of 3 jobs completed by {operator_name} in {cycle_time:.2f} seconds"
                print(f"\n{log_line}\n")
                logger.info(log_line)
                cycle_start = time.time()

            current_job += 1
            print(f"[System] Job {current_job - 1} complete. Waiting for next trigger...")

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

