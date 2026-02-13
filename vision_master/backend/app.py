from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from executor import run_workflow
import os
import json
import uuid
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECTS_DIR = os.path.join(BASE_DIR, "projects")

os.makedirs(PROJECTS_DIR, exist_ok=True)

app = Flask(__name__)
CORS(app)

@app.route("/")
def index():
    return send_from_directory("../html", "index.html")

@app.route("/js/<path:path>")
def js_files(path):
    return send_from_directory("../js", path)

@app.route("/styles.css")
def styles():
    return send_from_directory("..", "styles.css")

@app.route("/api/project/new", methods=["POST"])
def new_project():
    project_id = str(uuid.uuid4())
    data = {
        "id": project_id,
        "name": "Untitled_Project",
        "nodes": [],
        "connections": []
    }
    return jsonify(data)

@app.route("/api/project/save", methods=["POST"])
def save_project():
    project = request.json
    project_id = project.get("id", str(uuid.uuid4()))
    file_path = os.path.join(PROJECTS_DIR, f"{project_id}.json")

    with open(file_path, "w") as f:
        json.dump(project, f, indent=4)

    return jsonify({"status": "saved", "id": project_id})

@app.route("/api/project/load/<project_id>")
def load_project(project_id):
    file_path = os.path.join(PROJECTS_DIR, f"{project_id}.json")
    if not os.path.exists(file_path):
        return jsonify({"error": "Project not found"}), 404

    with open(file_path) as f:
        return jsonify(json.load(f))

@app.route("/api/project/demo")
def load_demo():
    demo_path = os.path.join(PROJECTS_DIR, "demo.json")
    if not os.path.exists(demo_path):
        return jsonify({
            "id": "demo",
            "name": "Demo_Project",
            "nodes": [],
            "connections": []
        })

    with open(demo_path) as f:
        return jsonify(json.load(f))

@app.route("/api/workflow/run", methods=["POST"])
def run_workflow_api():
    data = request.get_json(force=True)
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])

    start = time.time()
    results = run_workflow(nodes, edges)
    end = time.time()

    return jsonify({
        "results": results,
        "execution_time_ms": int((end - start) * 1000)
    })

@app.route("/api/status")
def status():
    return jsonify({
        "PLC": "Connected",
        "DSP": "Ready"
    })

if __name__ == "__main__":
    app.run(debug=True, port=5000)
