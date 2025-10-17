from flask import Flask, request, jsonify
import os
from dotenv import load_dotenv
import threading
from helpers import process_request

load_dotenv()

app = Flask(__name__)

@app.route('/')
def index():
    return "LLM Code Deployment Agent is running!"

@app.route('/api/request', methods=['POST'])
def handle_request():
    if not request.is_json:
        return jsonify({"error": "Invalid request: Content-Type must be application/json"}), 400

    data = request.get_json()
    secret = data.get('secret')

    if not secret or secret != os.environ.get('SHARED_SECRET'):
        return jsonify({"error": "Unauthorized"}), 401

    # Immediately respond and process in the background
    thread = threading.Thread(target=process_request, args=(data,))
    thread.start()

    return jsonify({"message": "Request received and is being processed"}), 200


if __name__ == '__main__':
    app.run(port=5000)