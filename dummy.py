import socket
import threading
import time
from gpiozero import Button
from gpiozero.pins.lgpio import LGPIOFactory
from datetime import datetime
import logging
from led_asms import LED_Asms

# Use LGPIO backend for Raspberry Pi 5
Button.pin_factory = LGPIOFactory()

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
RESET_PIN = 26     # GPIO22 for reset button

# ------------------------
# State Variables
# ------------------------
latest_result = {"timestamp": 0, "value": None}
current_job = 1
connected_sock = None
trigger_received = threading.Event()
trigger1_detected = threading.Event()
trigger2_detected = threading.Event()
reset_requested = threading.Event()
cycle_start = None
operator_name = ""
job_in_progress = False

# ------------------------
# LED instance
# ------------------------
led_job = LED_Asms()

# ------------------------
# GPIO Button Setup
# ------------------------
trigger1 = Button(TRIGGER1_PIN, pull_up=False)
trigger2 = Button(TRIGGER2_PIN, pull_up=False)
reset_btn = Button(RESET_PIN, pull_up=True)

# ------------------------
# Command Builders
# ------------------------
def build_command(job_number: int) -> bytes:
    cmd = f"set job {job_number}"
    print(f"[Debug] Sending command: {cmd}")
    return b'\x02' + cmd.encode('ascii') + b'\x03'

def build_trigger_command() -> bytes:
    return b'\x02trigger\x03'

# ------------------------
# Flush old result
# ------------------------
def flush_old_result():
    global latest_result
    latest_result = {"timestamp": 0, "value": None}

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
                    latest_result = {
                        "timestamp": time.time(),
                        "value": data.decode(errors='ignore').strip().lower()
                    }
    except Exception as e:
        print(f"[Result Thread] Error: {e}")

# ------------------------
# Trigger Handlers
# ------------------------
def on_trigger1():
    global job_in_progress
    if not job_in_progress:
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
        print(f" Sensor 1 (GPIO17) pulse detected at {ts}")
        trigger1_detected.set()
        check_dual_trigger()
    else:
        print(" Ignored trigger from Sensor 1 — job already in progress")

def on_trigger2():
    global job_in_progress
    if not job_in_progress:
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
        print(f" Sensor 2 (GPIO27) pulse detected at {ts}")
        trigger2_detected.set()
        check_dual_trigger()
    else:
        print(" Ignored trigger from Sensor 2 — job already in progress")

def check_dual_trigger():
    if trigger1_detected.is_set() and trigger2_detected.is_set():
        Dual_Trigger = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
        print(f" Both sensors triggered — proceeding to job at {Dual_Trigger}")
        trigger_received.set()

# ------------------------
# Reset Button Logic
# ------------------------
def on_reset():
    global reset_requested
    print("\n[RESET] Reset button pressed. Restarting the system...\n")
    reset_requested.set()

reset_btn.when_pressed = on_reset

# ------------------------
# Job Execution with Retry
# ------------------------
def run_job(job_number):
    global latest_result, connected_sock

    start_time = time.time()
    attempt = 0
    timeout = 6
    max_attempts = 5

    while attempt < max_attempts and not reset_requested.is_set():
        attempt += 1
        flush_old_result()

        try:
            job_cmd_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
            connected_sock.sendall(build_command(job_number))
            print(f" Job {job_number} switch command sent at {job_cmd_time}")
            time.sleep(1.5)

            flush_old_result()
            trig_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
            trigger_sent_time = time.time()
            connected_sock.sendall(build_trigger_command())
            print(f" Trigger command sent at {trig_time}")

            wait_start = time.time()
            while time.time() - wait_start < timeout:
                result_obj = latest_result
                if result_obj["timestamp"] > trigger_sent_time:
                    result = result_obj["value"]
                    print(f" [Raw Result] Received: {result}")

                    if "true" in result:
                        job_time = time.time() - start_time
                        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
                        print(f" /................... JOB {job_number} PASS....................../")
                        led_job.led_true_func()
                        msg = f"Job {job_number} completed by {operator_name} in {job_time:.2f}s with {attempt - 1} retries at {ts}"
                        print(f" {msg}")
                        logger.info(msg)
                        return True
                    elif "false" in result:
                        print(f"  Job {job_number} failed (Attempt {attempt}) — retrying...")
                        break
                    else:
                        print(f"  Unknown result: {result} — retrying")
                        break
                time.sleep(0.05)

            else:
                print(f"  Timeout waiting for result (Attempt {attempt}) — retrying...")

        except Exception as e:
            print(f"[Error] During job {job_number}: {e}")
            return False

    print(f"[Retry] Max retries ({max_attempts}) reached for Job {job_number}")
    return False

# ------------------------
# Main Function
# ------------------------
def main():
    global connected_sock, current_job, cycle_start, operator_name, job_in_progress

    trigger1.when_pressed = on_trigger1
    trigger2.when_pressed = on_trigger2

    while True:
        reset_requested.clear()
        current_job = 1
        job_in_progress = False
        trigger1_detected.clear()
        trigger2_detected.clear()
        trigger_received.clear()

        operator_name = input("Enter operator name: ").strip()
        print(f"[System] Operator: {operator_name}")
        logger.info(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}    --- New session started by {operator_name} ---")

        try:
            print(f"[Startup] Connecting to {CAMERA_IP}:{COMMAND_PORT} ...")
            connected_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            connected_sock.connect((CAMERA_IP, COMMAND_PORT))

            threading.Thread(target=result_listener, daemon=True).start()
            cycle_start = time.time()

            while not reset_requested.is_set():
                print("\n[Ready] Waiting for BOTH GPIO triggers...")
                trigger_received.wait()
                trigger_received.clear()

                if reset_requested.is_set():
                    break

                job_in_progress = True
                success = run_job(current_job)
                job_in_progress = False

                trigger1_detected.clear()
                trigger2_detected.clear()

                if success:
                    if current_job % 3 == 0:
                        cycle_time = time.time() - cycle_start
                        msg = f" Cycle of 3 jobs completed by {operator_name} in {cycle_time:.2f} seconds at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        print(f"\n[Cycle ] {msg}\n")
                        logger.info(msg)
                        cycle_start = time.time()
                    current_job += 1
                    print(f"[System] Job {current_job - 1} complete. Waiting for BOTH triggers again...")
                else:
                    print(f"[System] Max retries reached. Waiting to retry Job {current_job}...")

        except Exception as e:
            print(f"[Startup Error] {e}")
        finally:
            if connected_sock:
                connected_sock.close()
            print("[System] Socket closed. Restarting...")

if __name__ == "__main__":
    main()

