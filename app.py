import os 
import logging
import io
import threading
import time
import camera_manager
import cv2
import numpy as np
import json
from PIL import Image
from typing import Any, Dict, List, Tuple, Optional
from datetime import datetime, timedelta
from flask_cors import CORS
from flask import Flask, Response, render_template, flash, request, session, redirect, jsonify, url_for, send_file, abort
from flask import send_from_directory
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash
from database_manager import db_manager
from workflow_engine import run_workflow
from report_generated import generate_daily_report
from report_scheduler import start_scheduler
from image_processing import process_image_web, detect_edges, pixels_to_mm
from functools import wraps
from flask_apscheduler import APScheduler
from measurement_edge import detect_and_measure_edges, save_inspection
from inspection_engine import run_inspection
from camera_manager import (
    start_camera_service,
    stop_camera_service,
    get_latest_frame,
    set_exposure as cam_set_exposure,
    set_gain as cam_set_gain,
    set_trigger as cam_set_trigger,
    software_trigger as cam_software_trigger,
    capture_frame as camera_capture_frame
)
from apscheduler.schedulers.background import BackgroundScheduler

UPLOAD_FOLDER = os.path.join("static", "uploads")
TRAINED_IMAGES_FOLDER = os.path.join("static", "trained_images")
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff', 'tif', 'jfif'}
SESSION_TIMEOUT = 2  

last_daily_notification = {"message": None, "timestamp": None}
accepted_count = 0
rejected_count = 0
INSPECTIONS = []

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_client_ip():
    return request.headers.get("X-Forwarded-For", request.remote_addr)

def is_ip_allowed(client_ip: Optional[str], allowed_ips: Optional[str]) -> bool:
    if not client_ip or not allowed_ips:
        return False
    allowed_list = [ip.strip() for ip in allowed_ips.split(",")]
    return client_ip in allowed_list

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            flash("Please log in to access this page", "error")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def create_app():
    try:
        app = Flask(__name__, template_folder="templates", static_folder="static")
        app.secret_key = os.environ.get("SESSION_SECRET", "valve-inspection-secret-key")
        app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)
        app.config['SESSION_COOKIE_SECURE'] = False
        app.config['SESSION_COOKIE_HTTPONLY'] = True
        app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
        CORS(app)
        
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(TRAINED_IMAGES_FOLDER, exist_ok=True)

        app.config["CAMERA_INITIALIZED"] = False
        app.config["CAMERA_STATUS"] = {"software_open": False, "running": False}

        scheduler = BackgroundScheduler()
        scheduler.start()
        start_scheduler(app)

        logging.basicConfig(level=logging.INFO)

        @app.before_request
        def session_management():
            session.permanent = True
            now = datetime.now()
            if 'user' in session:
                last_activity = session.get('last_activity')
                if last_activity:
                    last_time = datetime.strptime(last_activity, "%Y-%m-%d %H:%M:%S")
                    if now - last_time > timedelta(hours=SESSION_TIMEOUT):
                        session.pop('user', None)
                        session.pop('last_activity', None)
                        flash("You have been logged out due to inactivity.", "info")
                        return redirect(url_for('login'))
                session['last_activity'] = now.strftime("%Y-%m-%d %H:%M:%S")

        def daily_notification():
            try:
                conn = db_manager.get_connection()
                if not conn:
                    app.logger.warning("No DB connection for daily notification")
                    return

                cursor = conn.cursor()
                today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                cursor.execute(
                    "SELECT COUNT(*) FROM inspections WHERE Result = 'Rejected' AND [timestamp] >= ?",
                    (today,)
                )
                row = cursor.fetchone()
                rejection_count = row[0] if row else 0

                global last_daily_notification
                last_daily_notification = {
                    "message": f"Check Maximum Defects. Please review.",
                    "timestamp": datetime.now()
                }
                app.logger.info("Daily notification triggered")

            except Exception as e:
                app.logger.error(f"Daily notification failed: {str(e)}")

        scheduler.add_job(
            daily_notification,
            'interval',
            minutes=30,
            id="daily_job"
        )

        @app.route("/")
        def login_page():
            return render_template("login.html")

        @app.route("/login", methods=["GET", "POST"])
        def login():
            if request.method == "POST":
                username = (request.form.get("username") or "").strip()
                password = (request.form.get("password") or "").strip()
                ip = get_client_ip()
                
                if not username or not password:
                    flash("Username and password required", "error")
                    return redirect("/login")
                
                if username == "admin" and password == "12345":
                    session.update({
                        "user": "admin",
                        "role": "ADMIN",
                        "location": "ALL",
                        "ip": ip
                    })
                    return redirect("/index")
                
                user = db_manager.get_user(username)
                if not user:
                    flash("Invalid username", "error")
                    return redirect("/login")

                if not user.get("is_active"):
                    flash("Waiting for admin approval", "warning")
                    return redirect("/login")

                if user.get("allowed_ip") and user["allowed_ip"] != ip:
                    flash("Login not allowed from this IP", "error")
                    return redirect("/login")

                if not check_password_hash(user["password_hash"], password):
                    flash("Invalid password", "error")
                    return redirect("/login")

                session.update({
                    "user": username,
                    "role": user["role"],
                    "location": user["location"],
                    "ip": ip
                })
                return redirect("/index")
                
            return render_template("login.html")

        @app.route("/logout")
        @login_required
        def logout():
            session.pop("user", None)
            flash("You have been logged out.", "success")
            return redirect(url_for('login'))

        @app.route("/profile")
        @login_required
        def profile():
            return render_template("profile.html", user=session.get("user"))

        @app.route("/home")
        def home():
            return render_template("home.html")

        @app.route("/index")
        @login_required
        def index():
            return render_template("index.html")

        @app.route("/dashboard")
        @login_required
        def dashboard():
            return render_template("dashboard.html")

        @app.route("/damage-dashboard")
        def damage_dashboard():
            return render_template("damage_dashboard.html")

        @app.route("/filter")
        @login_required
        def filter():
            return render_template("filter.html")

        @app.route("/training")
        def training_page():
            return render_template("training.html")

        @app.route("/valve-specs")
        @login_required
        def valve_specs_page():
            return render_template("valve_specs.html")

        @app.route("/flow-editor")
        def flow_editor():
            return render_template("flow_editor.html")

        @app.route("/control_panel")
        def control_panel():
            return render_template("control_panel.html")

        @app.route("/api/overview")
        def overview():
            return render_template("overview.html")

        @app.route("/video_feed")
        def video_feed():
            def generate():
                while True:
                    frame = get_latest_frame()
                    if frame is None:
                        time.sleep(0.05)
                        continue
                    _, buffer = cv2.imencode('.jpg', frame)
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")

        @app.route("/start_camera", methods=["POST"])
        def start_camera():
            try:
                start_camera_service(camera_type="webcam")
                cam_set_exposure(2079953)
                cam_set_gain(3.7)
                cam_set_trigger(True)
                return jsonify({"status": "started"})
            except Exception as e:
                app.logger.error(f"Failed to start camera: {str(e)}")
                return jsonify({"status": "error", "message": str(e)}), 500

        @app.route("/stop_camera", methods=["POST"])
        def stop_camera():
            try:
                stop_camera_service()
                return jsonify({"status": "stopped"})
            except Exception as e:
                app.logger.error(f"Failed to stop camera: {str(e)}")
                return jsonify({"status": "error", "message": str(e)}), 500

        @app.route("/capture_frame", methods=["POST"])
        def capture_frame_route():
            try:
                
                frame = camera_capture_frame()
                if frame is None:
                    return jsonify({"error": "Camera frame not available"}), 500
                original_name:str = secure_filename(file.filename)
                base_name,_ = os.path.splitext(original_name)  
                timestamp_str = datetime.now().strftime("_%S")  
                filename = f"{timestamp_str}_{base_name}.jpg"
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                cv2.imwrite(filepath, frame)
                app.logger.info(f"Frame captured and saved: {filename}")
                result, best_score, result_img_path, best_match, defect_type, part_number, part_name = process_image_web(
                    frame, filename
                )
                
                return jsonify({
                   "result": result,
                   "ssim": float(best_score) if best_score else None,
                   "img": url_for("serve_upload", filename=filename),
                   "image_name": filename,
                   "best_match": best_match,
                   "defect_type": defect_type,
                   "part_number": part_number,
                   "part_name": part_name
               })
            except Exception as e:
                app.logger.exception("Auto capture failed")
                return jsonify({"error": str(e)}), 500
            
        @app.route("/api/toggle_software", methods=["POST"])
        def toggle_software():
            status = app.config.get('CAMERA_STATUS', {})
            status['software_open'] = not status.get('software_open', False)
            return jsonify(status)

        @app.route("/api/trigger_camera", methods=["POST"])
        def trigger_camera():
            data = request.get_json() or {}
            object_type = data.get('object_type')
            status = app.config.get('CAMERA_STATUS', {})
            
            if object_type == 'engine_valve':
                if status.get('software_open'):
                    status['running'] = True
                    return jsonify({"message": "Camera Triggered", "status": status, "camera_running": True})
                else:
                    return jsonify({"message": "Software Closed", "status": status, "camera_running": False})
            
            return jsonify({"message": "Ignored", "status": status, "camera_running": False})

        @app.route("/set_exposure", methods=["POST"])
        def set_exposure():
            try:
                value = float(request.json["value"])
                cam_set_exposure(value)
                return {"status": "ok"}
            except Exception as e:
                return {"status": "error", "message": str(e)}, 500

        @app.route("/set_gain", methods=["POST"])
        def set_gain():
            try:
                value = float(request.json["value"])
                cam_set_gain(value)
                return {"status": "ok"}
            except Exception as e:
                return {"status": "error", "message": str(e)}, 500

        @app.route("/set_trigger", methods=["POST"])
        def set_trigger():
            try:
                value = bool(request.json["value"])
                cam_set_trigger(value)
                return {"status": "ok"}
            except Exception as e:
                return {"status": "error", "message": str(e)}, 500

        @app.route("/software_trigger", methods=["POST"])
        def software_trigger():
            try:
                cam_software_trigger()
                return {"status": "ok"}
            except Exception as e:
                return {"status": "error", "message": str(e)}, 500
            
        @app.route("/upload", methods=["POST"])
        def upload():
        
          try:
            if "image" not in request.files:
                return jsonify({"error": "No image uploaded"}), 400

            file = request.files["image"]
            if not file or not file.filename:
                return jsonify({"error": "No filename"}), 400

            original_name:str = secure_filename(file.filename)
            base_name,_ = os.path.splitext(original_name)  
            timestamp_str = datetime.now().strftime("_%S")  
            filename = f"{timestamp_str}_{base_name}.jpg"
            filepath = os.path.join(UPLOAD_FOLDER, filename)

            img = Image.open(file.stream).convert("RGB")
            img.save(filepath, "JPEG", quality=90)

            frame = cv2.imread(filepath)
            if frame is None:
                return jsonify({"error": "Failed to read saved image"}), 500

            result, best_score, result_img_path, best_match, defect_type, part_number, part_name = process_image_web(frame, filename)

            payload = {
                "result": result,
                "ssim": float(best_score) if best_score is not None else None,
                "img": url_for("serve_upload", filename=filename),
                "image_name": filename,           
                "best_match": best_match,
                "defect_type": defect_type,
                "part_number": part_number,
                "part_name": part_name
            }

            return jsonify(payload)

          except Exception as e:
            app.logger.exception("Upload processing failed")
            return jsonify({"error": str(e)}), 500

        @app.route("/save_inspection", methods=["POST"])
        def save_inspection_route():
            try:
                data = request.get_json()
                if not data:
                    return jsonify({"error": "JSON body required"}), 400

                location = data.get("location") or "Unknown"
                shifts = data.get("shifts") or "Unknown"
                image_name = data.get("image_name")
                if image_name and image_name.startswith("/"):
                    image_name = os.path.basename(image_name)
                def safe_float(val):
                    try:
                        return float(val)
                    except (TypeError, ValueError):
                        return 0.0
                    
                def safe_str(val, default="Unknown"):
                    if val is None or str(val).strip() == "":
                        return default
                    return str(val).strip()
                
                db_payload = {
                    "part_number": data.get("part_number"),
                    "part_name": data.get("part_name"),
                    "image_name": image_name,
                    "ssim_score": data.get("ssim_score"),
                    "result": data.get("result"),
                    "best_match": data.get("best_match"),
                    "defect_type": data.get("defect_type"),
                    "timestamp": data.get("timestamp") or datetime.now(),
                    "location": location,
                    "shifts": shifts,
                    "Core_Hardness_stem": float(data.get("Core_Hardness_stem") or 0),
                    "Crown_Face_runout": float(data.get("Crown_Face_runout") or 0),
                    "Datum_to_End": float(data.get("Datum_to_End") or 0),
                    "End_Finish": float(data.get("End_Finish") or 0),
                    "End_Radius": float(data.get("End_Radius") or 0),
                    "Groove_Diameter": float(data.get("Groove_Diameter") or 0),
                    "Groove_Chamfer_Angle": float(data.get("Groove_Chamfer_Angle") or 0),
                    "Head_Diameter": float(data.get("Head_Diameter") or 0),
                    "Neck_Diameter": float(data.get("Neck_Diameter") or 0),
                    "Overall_Length": float(data.get("Overall_Length") or 0),
                    "Stem_Diameter": float(data.get("Stem_Diameter") or 0),
                    "Seat_Angle": float(data.get("Seat_Angle") or 0),
                    "Surface_Hardness_Nitriding": float(data.get("Surface_Hardness_Nitriding") or 0),
                }
                
                inserted_id = db_manager.insert_inspection(db_payload)
                return jsonify({"status": "success", "id": inserted_id})

            except ValueError as ve:
                app.logger.error("Validation error saving inspection: %s", ve)
                return jsonify({"error": str(ve)}), 400

            except Exception as e:
                app.logger.exception("Failed to save inspection")
                return jsonify({"error": str(e)}), 500

        @app.route("/inspect", methods=["POST"])
        def inspect():
            success = run_inspection()
            return jsonify({"success": success})

        @app.route("/inspection/<part_number>")
        def inspection_details(part_number):
            try:
                conn = db_manager.get_connection()
                if not conn:
                    return jsonify({"error": "Database connection not available"}), 500

                cursor = conn.cursor()
                cursor.execute("""
                    SELECT TOP 1 Part_number, Image_name, Result, ssim_score, Defect_type, Best_match, timestamp
                    FROM inspections
                    WHERE Part_number = ?
                    ORDER BY timestamp DESC
                """, (part_number,))
                row = cursor.fetchone()

                if not row:
                    return render_template("inspection_details.html", error="No inspections found")

                base_name = row[1]
                uploads_folder = os.path.join("static", "uploads")
                for ext in [".jpg", ".jpeg", ".png"]:
                    candidate = os.path.join(uploads_folder, base_name + ext)
                    if os.path.exists(candidate):
                        base_name = base_name + ext
                        break
                        
                inspection = {
                    "part_number": row[0],
                    "image_name": row[1],
                    "result": row[2],
                    "ssim_score": round(row[3], 4) if row[3] else None,
                    "defect_type": row[4],
                    "trained_image": row[5],
                    "timestamp": row[6]
                }

                return render_template("inspection_details.html", inspection=inspection)

            except Exception as e:
                return jsonify({"error": str(e)}), 500

        @app.route("/inspection/query")
        def inspection_query():
            part_number = request.args.get("part_number")
            if not part_number:
                return "Part number not provided", 400
            return redirect(url_for("inspection_details", part_number=part_number))

        @app.route("/inspection/")
        def inspection_index():
            try:
                conn = db_manager.get_connection()
                if not conn:
                    return "Database connection not available", 500

                cursor = conn.cursor()
                cursor.execute("""
                    SELECT TOP 1 Part_number, Image_name, Result, ssim_score, Defect_type, Best_match, timestamp
                    FROM inspections
                    ORDER BY timestamp DESC
                """)
                row = cursor.fetchone()

                if row:
                    inspection = {
                        "part_number": row[0],
                        "image_name": row[1],
                        "result": row[2],
                        "ssim_score": round(row[3], 4) if row[3] else None,
                        "defect_type": row[4],
                        "trained_image": row[5],
                        "timestamp": row[6]
                    }
                    return render_template("inspection_details.html", inspection=inspection)

                return "No inspections found"

            except Exception as e:
                return jsonify({"error": str(e)}), 500

        @app.route("/api/data")
        def dashboard_data():
            try:
                conn = db_manager.get_connection()
                if not conn:
                    return jsonify({"error": "Database connection not available"}), 500

                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM inspections WHERE Result = 'Accepted'")
                row = cursor.fetchone()
                accepted = row[0] if row else 0

                cursor.execute("SELECT COUNT(*) FROM inspections WHERE Result = 'Rejected'")
                row = cursor.fetchone()
                rejected = row[0] if row else 0

                total = accepted + rejected
                return jsonify({"accepted": accepted, "rejected": rejected, "total": total})
                
            except Exception as e:
                return jsonify({"error": f"Dashboard fetch failed: {str(e)}"}), 500

        @app.route("/api/daily-notification")
        def get_daily_notification():
            global last_daily_notification
            if last_daily_notification["message"]:
                return jsonify(last_daily_notification)
            return jsonify({"message": None, "timestamp": None})

        @app.route("/api/rejected-data/<filter_type>")
        def get_rejected_data(filter_type):
            try:
                conn = db_manager.get_connection()
                if not conn:
                    return jsonify({"error": "Database connection not available"}), 500
                    
                cursor = conn.cursor()
                now = datetime.utcnow()

                if filter_type == "daily":
                    start_date = datetime(now.year, now.month, now.day)
                elif filter_type == "weekly":
                    start_date = now - timedelta(days=7)
                elif filter_type == "monthly":
                    start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                elif filter_type == "3months":
                    start_date = datetime(now.year, now.month, 1) - timedelta(days=90)
                elif filter_type == "6months":
                    start_date = datetime(now.year, now.month, 1) - timedelta(days=180)
                elif filter_type == "yearly":
                    start_date = datetime(now.year - 1, now.month, now.day)
                else:
                    return jsonify({"error": "Invalid filter type"}), 400

                cursor.execute("""
                    SELECT Part_number, Result, Defect_type, [timestamp]
                    FROM inspections
                    WHERE Result = 'Rejected' AND [timestamp] >= ?
                """, (start_date,))
                rows = cursor.fetchall()
                columns = [col[0] for col in cursor.description]
                data = [{col: row[i] for i, col in enumerate(columns)} for row in rows]
                
                return jsonify(data)
                
            except Exception as e:
                return jsonify({"error": f"Failed to fetch rejected data: {str(e)}"}), 500

        @app.route("/api/chart-data")
        def chart_data():
            try:
                location = (request.args.get("location") or "").lower()
                part_number = (request.args.get("part_number") or "").lower()
                shift = (request.args.get("shift") or "").lower()
                time_filter = (request.args.get("time_filter") or "").lower()
                
                if location.lower().replace(" ", "") in ["allplants", "all"]:
                    location = ""
                if shift.lower().replace(" ", "") in ["allshifts", "all"]:
                    shift = ""
                if time_filter in ["", "?", None]:
                    time_filter = "daily"
                if part_number.lower() in ["none", "null"]:
                    part_number = ""

                conn = db_manager.get_connection()
                if not conn:
                    return jsonify({"error": "Database connection not available"}), 500
                    
                cursor = conn.cursor()
                now = datetime.now()

                if time_filter == "daily":
                    start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
                elif time_filter == "weekly":
                    start_time = now - timedelta(days=7)
                elif time_filter == "monthly":
                    start_time = now - timedelta(days=30)
                elif time_filter == "yearly":
                    start_time = now - timedelta(days=365)
                else:
                    start_time = now - timedelta(days=1)

                query = """
                    SELECT 
                        SUM(CASE WHEN Result='Accepted' THEN 1 ELSE 0 END) AS accepted,
                        SUM(CASE WHEN Result='Rejected' THEN 1 ELSE 0 END) AS rejected,
                        COUNT(*) AS total
                    FROM inspections
                    WHERE [Timestamp] >= ?
                """
                params: List[Any] = [start_time]

                if location and location != "":
                    query += " AND Location = ?"
                    params.append(location)
                if shift and shift != "":
                    query += " AND Shifts = ?"
                    params.append(shift)
                if part_number and part_number != "" and part_number.lower() != "none":
                    query += " AND Part_number = ?"
                    params.append(part_number)

                cursor.execute(query, params)
                row = cursor.fetchone()

                if row is None:
                    accepted = rejected = total = 0
                else:
                    accepted = row[0] or 0
                    rejected = row[1] or 0
                    total = row[2] or 0

                cursor.close()
                conn.close()

                return jsonify({
                    "accepted": accepted,
                    "rejected": rejected,
                    "total": total
                })
                
            except Exception as e:
                return jsonify({"error": f"Failed to fetch chart data: {str(e)}"}), 500

        @app.route("/api/defect-types")
        def get_defect_types():
            try:
                part_number = request.args.get("part", "").strip()
                time_range = request.args.get("time", "").strip().lower()
                
                conn = db_manager.get_connection()
                if not conn:
                    return jsonify({"error": "Database connection error"}), 500
                    
                cursor = conn.cursor()
                now = datetime.now()
                start = None

                if time_range == "daily":
                    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                elif time_range == "weekly":
                    monday = now - timedelta(days=now.weekday())
                    start = monday.replace(hour=0, minute=0, second=0, microsecond=0)
                elif time_range == "monthly":
                    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                elif time_range == "yearly":
                    start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

                query = """
                    SELECT Defect_type, COUNT(*) 
                    FROM inspections 
                    WHERE Result = 'Rejected'
                """
                params = []

                if part_number:
                    query += " AND part_number = ?"
                    params.append(part_number)
                if start:
                    query += " AND [timestamp] >= ?"
                    params.append(start)
                query += " GROUP BY Defect_type"
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                data = [
                    {"label": row[0], "count": row[1]}
                    for row in rows
                    if row[0] not in (None, "", "Defect")
                ]

                return jsonify({
                    "part_number": part_number,
                    "time_range": time_range,
                    "data": data,
                })

            except Exception as e:
                return jsonify({"error": f"Defect type fetch error: {str(e)}"}), 500

        @app.route("/api/valve-specs", methods=["GET"])
        def valve_specs():
            part_number = request.args.get("part_number")
            if not part_number:
                return "Part number is required", 400

            try:
                conn = db_manager.get_connection()
                if conn is None:
                    return jsonify({"error": "Database connection not available"}), 500
                    
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT *
                    FROM Valve_Details
                    WHERE [Part Number] = ?
                """, (part_number,))
                row = cursor.fetchone()

                if not row:
                    cursor.close()
                    conn.close()
                    return f"No data found for Part Number {part_number}", 404
                    
                columns = [col[0] for col in cursor.description]
                specs = {col: row[i] for i, col in enumerate(columns)}

                cursor.close()
                conn.close()
                return jsonify(specs)

            except Exception as e:
                app.logger.error(f"Failed to fetch valve specs: {str(e)}")
                return f"Error fetching valve specs: {str(e)}", 500

        @app.route("/api/reports/daily", methods=["GET"])
        def download_daily_report():
            try:
                date_str = request.args.get("date")
                out_format = request.args.get("format", "xlsx").lower()
                
                if date_str:
                    date_from = datetime.strptime(date_str, "%Y-%m-%d")
                else:
                    today = datetime.now()
                    date_from = datetime(today.year, today.month, today.day)
                    
                date_from = datetime.combine(date_from.date(), datetime.min.time())
                date_to = date_from + timedelta(days=1)
                
                df = db_manager.fetch_inspections(date_from=date_from, date_to=date_to)
                
                if df.empty:
                    return jsonify({"error": "No inspection data found for selected date"}), 404
                    
                out_path, _summary = generate_daily_report(df, date_from, date_from + timedelta(days=1), out_format)
                return send_file(
                    out_path,
                    as_attachment=True,
                    download_name=os.path.basename(out_path),
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            except Exception as e:
                app.logger.exception("[Daily Report Error]")
                return jsonify({"error": str(e)}), 500

        @app.route("/api/reports/range", methods=["GET"])
        def download_range_report():
            try:
                df_str = request.args.get("date_from")
                dt_str = request.args.get("date_to")
                out_format = request.args.get("format", "xlsx").lower()
                
                if not df_str or not dt_str:
                    return jsonify({"error": "Please provide date_from and date_to (YYYY-MM-DD)"}), 400
                    
                dfrom = datetime.strptime(df_str, "%Y-%m-%d")
                dto = datetime.strptime(dt_str, "%Y-%m-%d") + timedelta(days=1)
                df = db_manager.fetch_inspections(dfrom, dto)

                if df.empty:
                    return jsonify({"error": "No inspection data found for selected date range"}), 404
                    
                out_path, summary = generate_daily_report(df, date_from=dfrom, date_to=dto, out_format=out_format)
                return send_file(
                    out_path,
                    as_attachment=True,
                    download_name=os.path.basename(out_path),
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            except Exception as e:
                app.logger.exception("[Range Report Error]")
                return jsonify({"error": str(e)}), 500

        @app.route("/api/reports/dashboard-download", methods=["GET"])
        @login_required
        def download_dashboard_report():
            try:
                location = (request.args.get("location") or "").strip()
                shift = (request.args.get("shift") or "").strip()
                part_number = (request.args.get("part_number") or "").strip()
                time_filter = (request.args.get("time_filter") or "daily").lower()

                user_role = session.get("role", "PLANT_HEAD")
                user_location = session.get("location", "")

                if user_role != "ADMIN" and user_location:
                    location = user_location

                now = datetime.now()
                if time_filter == "daily":
                    start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
                elif time_filter == "weekly":
                    start_time = now - timedelta(days=7)
                elif time_filter == "monthly":
                    start_time = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                elif time_filter == "yearly":
                    start_time = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
                else:
                    start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)

                df = db_manager.fetch_filtered_inspections(
                    start_time=start_time,
                    location=location,
                    shift=shift,
                    part_number=part_number
                )

                if df.empty:
                    return jsonify({"error": "No data found for selected filters"}), 404
                    
                output = io.BytesIO()
                df.to_excel(output, index=False)
                output.seek(0)
                filename = f"dashboard_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                
                return send_file(
                    output,
                    as_attachment=True,
                    download_name=filename,
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            except Exception as e:
                app.logger.exception("Dashboard report download failed")
                return jsonify({"error": str(e)}), 500

        @app.route("/download_excel")
        def download_excel():
            df = db_manager.fetch_inspections(date_from=None, date_to=None)
            output = io.BytesIO()
            df.to_excel(output, index=False)
            output.seek(0)
            return send_file(
                output,
                as_attachment=True,
                download_name="inspections.xlsx",
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        
        @app.route("/api/train-edges", methods=["POST"])
        def train_edges():
            try:
                from image_processing import train_reference_edges, get_edge_visualization

                part_number = request.form.get("part_number")
                if not isinstance(part_number, str) or not part_number.strip():
                    return jsonify({"error": "Invalid or missing part_number"}), 400
                    
                if "image" not in request.files:
                    return jsonify({"error": "No image uploaded"}), 400

                file = request.files["image"]
                if not file or not file.filename:
                    return jsonify({"error": "No image selected"}), 400

                original_name: str = secure_filename(file.filename)
                if not original_name:
                    return jsonify({"error": "Invalid filename"}), 400
                    
                part_folder = os.path.join(TRAINED_IMAGES_FOLDER, part_number)
                os.makedirs(part_folder, exist_ok=True)

                filepath = os.path.join(part_folder, original_name)

                img = Image.open(file.stream).convert("RGB")
                img.save(filepath, "JPEG")

                result_img, features = train_reference_edges(part_number, filepath)

                if result_img is None or not isinstance(result_img, np.ndarray):
                    return jsonify({"error": "Failed to extract edges from image"}), 500

                if not isinstance(features, dict):
                    return jsonify({"error": "Invalid features returned"}), 500

                viz_path: str = os.path.join(
                    "static",
                    "uploads",
                    f"trained_{part_number}_{original_name}"
                )
                cv2.imwrite(viz_path, result_img)

                return jsonify({
                    "success": True,
                    "message": f"Trained edges for part {part_number}",
                    "visualization": url_for("static", filename=f"uploads/trained_{part_number}_{original_name}"),
                    "features": {
                        "area": float(features.get("area", 0.0)),
                        "perimeter": float(features.get("perimeter", 0.0)),
                        "aspect_ratio": float(features.get("aspect_ratio", 0.0)),
                        "solidity": float(features.get("solidity", 0.0))
                    }
                })

            except Exception as e:
                app.logger.error(f"Edge training error: {str(e)}")
                return jsonify({"error": str(e)}), 500

        @app.route("/api/view-edges/<part_number>")
        def view_edges(part_number):
            try:
                from image_processing import get_edge_visualization

                part_folder = os.path.join(TRAINED_IMAGES_FOLDER, part_number)
                if not os.path.exists(part_folder):
                    return jsonify({"error": f"Part {part_number} not found"}), 404

                images = []
                for img_file in os.listdir(part_folder):
                    if img_file.lower().endswith(('.png', '.jpg', '.jpeg', '.jfif', '.bmp')):
                        img_path = os.path.join(part_folder, img_file)
                        viz = get_edge_visualization(img_path)
                        if viz is not None:
                            viz_filename = f"edges_{part_number}_{img_file}"
                            viz_path = os.path.join("static/uploads", viz_filename)
                            cv2.imwrite(viz_path, viz)
                            images.append({
                                "original": url_for("static", filename=f"trained_images/{part_number}/{img_file}"),
                                "edges": url_for("static", filename=f"uploads/{viz_filename}")
                            })

                return jsonify({
                    "part_number": part_number,
                    "images": images
                })

            except Exception as e:
                app.logger.error(f"View edges error: {str(e)}")
                return jsonify({"error": str(e)}), 500

        @app.route("/api/trained-parts")
        def list_trained_parts():
            try:
                parts = []
                if os.path.exists(TRAINED_IMAGES_FOLDER):
                    for part_folder in os.listdir(TRAINED_IMAGES_FOLDER):
                        part_path = os.path.join(TRAINED_IMAGES_FOLDER, part_folder)
                        if os.path.isdir(part_path):
                            image_count = len([f for f in os.listdir(part_path)
                                             if f.lower().endswith(('.png', '.jpg', '.jpeg', '.jfif', '.bmp'))])
                            parts.append({
                                "part_number": part_folder,
                                "image_count": image_count
                            })

                return jsonify({"parts": parts})

            except Exception as e:
                app.logger.error(f"List trained parts error: {str(e)}")
                return jsonify({"error": str(e)}), 500

        @app.route("/api/workflow/run", methods=["POST"])
        def run():
            data = request.get_json(silent=True)
            if data is None:
                return jsonify({"error": "Invalid or missing JSON body"}), 400

            nodes: List[Dict[str, Any]] = data.get("nodes", [])
            edges: List[Dict[str, Any]] = data.get("edges", [])
            start = time.time()
            results = run_workflow(nodes, edges)
            end = time.time()

            return jsonify({
                "node_results": results,
                "execution_time_ms": int((end - start) * 1000)
            })

        @app.route("/admin/pending-users")
        @login_required
        def pending_users():
            if session.get("role") != "ADMIN":
                abort(403)
            return jsonify(db_manager.get_pending_users())

        @app.route("/admin/approve/<username>", methods=["POST"])
        @login_required
        def approve(username):
            if session.get("role") != "ADMIN":
                abort(403)
            db_manager.approve_user(username)
            return jsonify({"status": "approved"})

        @app.route('/uploads/<filename>')
        def serve_upload(filename):
            return send_from_directory(UPLOAD_FOLDER, filename)

        @app.route('/trained_images/<part_number>/<filename>')
        def serve_trained_image(part_number, filename):
            folder = os.path.join(TRAINED_IMAGES_FOLDER, part_number)
            return send_from_directory(folder, filename)

        return app

    except Exception as e:
        logging.exception("Failed to create app")
        return None  