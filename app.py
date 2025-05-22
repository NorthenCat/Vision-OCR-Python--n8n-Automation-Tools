import os
import json
from flask import Flask, request, redirect, render_template
import requests
from Quartz import CGImageSourceCreateWithURL, CGImageSourceCreateImageAtIndex
import CoreFoundation
import Vision

app = Flask(__name__)
UPLOAD_FOLDER = './uploads'
DATA_FILE = 'data.json'
N8N_WEBHOOK_URL = 'http://localhost:5678/webhook/8eaf855b-ba32-4daa-ba99-2f25a4649b95'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def load_data():
    if not os.path.exists(DATA_FILE):
        return {'pending': [], 'sent': []}
    with open(DATA_FILE, 'r') as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def extract_text_vision(image_path):
    url = CoreFoundation.CFURLCreateWithFileSystemPath(
        None, image_path, CoreFoundation.kCFURLPOSIXPathStyle, False
    )
    imageSource = CGImageSourceCreateWithURL(url, None)
    imageRef = CGImageSourceCreateImageAtIndex(imageSource, 0, None)

    request = Vision.VNRecognizeTextRequest.alloc().initWithCompletionHandler_(None)
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)

    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(imageRef, None)
    success, error = handler.performRequests_error_([request], None)

    if not success:
        return "OCR Failed"

    results = request.results()
    texts = []
    for r in results:
        candidate = r.topCandidates_(1).firstObject()
        if candidate:
            texts.append(str(candidate.string()))

    return "\n".join(texts)

@app.route('/', methods=['GET', 'POST'])
def upload_files():
    data = load_data()

    if request.method == 'POST':
        files = request.files.getlist('photos')
        for f in files:
            filepath = os.path.join(UPLOAD_FOLDER, f.filename)
            f.save(filepath)

            text = extract_text_vision(filepath)
            payload = {'filename': f.filename, 'text': text}

            try:
                r = requests.post(N8N_WEBHOOK_URL, json=payload)
                if r.status_code == 200:
                    data['sent'].append({'filename': f.filename, 'text': text})
                    os.remove(filepath)  # Delete after successful send
                else:
                    data['pending'].append({'filename': f.filename, 'error': f"HTTP {r.status_code}"})
            except Exception as e:
                data['pending'].append({'filename': f.filename, 'error': str(e)})

        save_data(data)
        return redirect('/')

    return render_template('index.html', pending_files=data['pending'], sent_files=data['sent'])

@app.route('/reset', methods=['POST'])
def reset_data():
    save_data({'pending': [], 'sent': []})
    # Optionally delete all uploaded files
    for f in os.listdir(UPLOAD_FOLDER):
        os.remove(os.path.join(UPLOAD_FOLDER, f))
    return redirect('/')

@app.route('/resend', methods=['POST'])
def resend_files():
    data = load_data()
    still_pending = []

    for file in data['pending']:
        filepath = os.path.join(UPLOAD_FOLDER, file['filename'])
        if not os.path.exists(filepath):
            file['error'] = 'File not found'
            still_pending.append(file)
            continue

        text = extract_text_vision(filepath)
        payload = {'filename': file['filename'], 'text': text}

        try:
            r = requests.post(N8N_WEBHOOK_URL, json=payload)
            if r.status_code == 200:
                data['sent'].append({'filename': file['filename'], 'text': text})
                os.remove(filepath)
            else:
                still_pending.append({'filename': file['filename'], 'error': f"HTTP {r.status_code}"})
        except Exception as e:
            still_pending.append({'filename': file['filename'], 'error': str(e)})

    data['pending'] = still_pending
    save_data(data)
    return redirect('/')

if __name__ == '__main__':
    app.run(port=5000, debug=True)
