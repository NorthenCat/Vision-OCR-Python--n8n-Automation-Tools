import os
import json
from flask import Flask, request, redirect, render_template
import requests
from Quartz import CGImageSourceCreateWithURL, CGImageSourceCreateImageAtIndex
import CoreFoundation
import Vision
import cv2

app = Flask(__name__)
UPLOAD_FOLDER = './uploads'
DATA_FILE = 'data.json'
N8N_WEBHOOK_URL = 'http://localhost:5678/webhook-test/8eaf855b-ba32-4daa-ba99-2f25a4649b95'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def load_data():
    if not os.path.exists(DATA_FILE):
        return {'pending': [], 'sent': []}
    with open(DATA_FILE, 'r') as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def preprocess_image(image_path):
    """
    Preprocess the image by converting it to grayscale and enhancing it for better readability.
    """
    image = cv2.imread(image_path)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)  # Convert to grayscale
    
    #make text more black
    # Increase contrast
    gray = cv2.addWeighted(gray, 1.5, gray, 0, -100)

    # Use bilateral filtering to preserve edges while smoothing
    enhanced = cv2.bilateralFilter(gray, 9, 0, 50)
    
    
    processed_path = image_path.replace('.jpg', '_processed.jpg').replace('.png', '_processed.png')
    cv2.imwrite(processed_path, enhanced)
    return processed_path

def extract_text_vision(image_path):
    # Preprocess the image before OCR
    preprocessed_path = preprocess_image(image_path)
    url = CoreFoundation.CFURLCreateWithFileSystemPath(
        None, preprocessed_path, CoreFoundation.kCFURLPOSIXPathStyle, False
    )
    imageSource = CGImageSourceCreateWithURL(url, None)
    imageRef = CGImageSourceCreateImageAtIndex(imageSource, 0, None)

    request = Vision.VNRecognizeTextRequest.alloc().initWithCompletionHandler_(None)
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)

    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(imageRef, None)
    success, error = handler.performRequests_error_([request], None)

    if not success:
        return "OCR Failed"
    
    #remove the preprocessed image
    os.remove(preprocessed_path)

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
        temp_data = {'pending': [], 'sent': []}
        files = request.files.getlist('photos')
        for f in files:
            filepath = os.path.join(UPLOAD_FOLDER, f.filename)
            f.save(filepath)

            # Preprocess and extract text
            text = extract_text_vision(filepath)
            temp_data['pending'].append({'filename': f.filename, 'raw': text, 'error': None})

            # Remove the uploaded file after processing
            os.remove(filepath)

        # POST each pending file to N8N webhook
        for file in temp_data['pending']:
            payload = {'filename': file['filename'], 'text': file['raw']}
            try:
                r = requests.post(N8N_WEBHOOK_URL, json=payload)
                response_json = r.json()  # Parse the response JSON
                print(f"Raw Response JSON: {response_json}")  # Debug log

                # Safeguard: Check if the response structure matches the expected format
                if r.status_code == 200 and isinstance(response_json, list):
                    for response in response_json:
                        if response.get('code') == 200:
                            data['sent'].append({'filename': file['filename'], 'text': file['raw']})
                        else:
                            error_message = response.get('body', {}).get('message', 'Unknown error')
                            data['pending'].append({'filename': file['filename'], 'raw': file['raw'], 'error': f"HTTP {response.get('code', 'N/A')}, {error_message}"})
                        save_data(data)
                else:
                    # Handle unexpected response format
                    data['pending'].append({'filename': file['filename'], 'raw': file['raw'], 'error': 'Unexpected response format'})
                    save_data(data)
            except Exception as e:
                print(f"Error: {str(e)}")
                data['pending'].append({'filename': file['filename'], 'raw': file['raw'], 'error': str(e)})
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
        # Check if "raw" data exists
        if not file.get('raw'):
            filepath = os.path.join(UPLOAD_FOLDER, file['filename'])
            if not os.path.exists(filepath):
                file['error'] = 'File not found'
                still_pending.append(file)
                continue

            # Preprocess and extract text if "raw" is empty
            file['raw'] = extract_text_vision(filepath)
            os.remove(filepath)

        payload = {'filename': file['filename'], 'text': file['raw']}

        print(f"Resending {file['filename']} to {N8N_WEBHOOK_URL}")
        try:
            r = requests.post(N8N_WEBHOOK_URL, json=payload)
            response_json = r.json()  # Parse the response JSON
            print(f"Raw Response JSON: {response_json}")  # Debug log

            # Safeguard: Check if the response structure matches the expected format
            if r.status_code == 200 and isinstance(response_json, list):
                for response in response_json:
                    if response.get('code') == 200:
                        data['sent'].append({'filename': file['filename'], 'text': file['raw']})
                    else:
                        error_message = response.get('body', {}).get('message', 'Unknown error')
                        still_pending.append({'filename': file['filename'], 'raw': file['raw'], 'error': f"HTTP {response.get('code', 'N/A')}, {error_message}"})
            else:
                # Handle unexpected response format
                still_pending.append({'filename': file['filename'], 'raw': file['raw'], 'error': 'Unexpected response format'})
        except Exception as e:
            print(f"Error: {str(e)}")
            still_pending.append({'filename': file['filename'], 'raw': file['raw'], 'error': str(e)})

    data['pending'] = still_pending
    save_data(data)
    return redirect('/')

if __name__ == '__main__':
    app.run(port=5000, debug=True)
