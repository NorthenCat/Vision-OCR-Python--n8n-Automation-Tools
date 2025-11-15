import os
import json
from flask import Flask, request, redirect, render_template, jsonify
import requests
from Quartz import CGImageSourceCreateWithURL, CGImageSourceCreateImageAtIndex
import CoreFoundation
import Vision
import cv2
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

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
    # Extract text from image without preprocessing
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

def extract_text_vision_raw(image_path):
    """
    Extract text from image without any preprocessing
    """
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
        temp_data = {'pending': [], 'sent': []}
        files = request.files.getlist('photos')
        
        # Check if user wants to skip N8N posting
        skip_n8n = request.form.get('skip_n8n') == 'on'
        
        for f in files:
            filepath = os.path.join(UPLOAD_FOLDER, f.filename)
            f.save(filepath)

            # Preprocess and extract text
            text = extract_text_vision(filepath)
            temp_data['pending'].append({'filename': f.filename, 'raw': text, 'error': None})

            # Remove the uploaded file after processing
            os.remove(filepath)

        # If skip N8N is enabled, directly save to sent without posting
        if skip_n8n:
            for file in temp_data['pending']:
                data['sent'].append({'filename': file['filename'], 'text': file['raw']})
            save_data(data)
        else:
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

@app.route('/excel-manager')
def excel_manager():
    data = load_data()
    return render_template('excel_manager.html', sent_files=data['sent'])

@app.route('/ocr-test')
def ocr_test():
    return render_template('ocr_test.html')

@app.route('/jsonl-formatter')
def jsonl_formatter():
    return render_template('jsonl_formatter.html')

@app.route('/upload-excel', methods=['POST'])
def upload_excel():
    if 'excel_file' not in request.files:
        return jsonify({'error': 'No file selected'}), 400
    
    file = request.files['excel_file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file and file.filename.endswith(('.xlsx', '.xls')):
        # Save the uploaded Excel file
        excel_path = os.path.join(UPLOAD_FOLDER, 'uploaded_excel.xlsx')
        file.save(excel_path)
        return jsonify({'success': 'Excel file uploaded successfully', 'path': excel_path})
    
    return jsonify({'error': 'Please upload a valid Excel file (.xlsx or .xls)'}), 400

@app.route('/add-to-excel', methods=['POST'])
def add_to_excel():
    try:
        from openpyxl import load_workbook
        
        # Get data from request
        selected_files = request.json.get('selected_files', [])
        excel_path = os.path.join(UPLOAD_FOLDER, 'uploaded_excel.xlsx')
        
        if not os.path.exists(excel_path):
            return jsonify({'error': 'Please upload an Excel file first'}), 400
        
        if not selected_files:
            return jsonify({'error': 'Please select at least one file'}), 400
        
        # Load the data.json
        data = load_data()
        
        # Create a mapping of filename to text
        text_mapping = {}
        for file in data['sent']:
            if file['filename'] in selected_files:
                text_mapping[file['filename']] = file['text']
        
        # Load the Excel workbook
        workbook = load_workbook(excel_path)
        sheet = workbook.active
        
        # Update rows based on filename matching
        # Filename is in column B (index 2), RAW DATA is in column BY (index 77)
        updated_count = 0
        row_num = 2  # Start from row 2 (assuming row 1 is header)
        
        while sheet[f'B{row_num}'].value is not None:
            filename = str(sheet[f'B{row_num}'].value).strip()
            if filename in text_mapping:
                sheet[f'BY{row_num}'] = text_mapping[filename]
                updated_count += 1
            row_num += 1
        
        # Save the updated Excel file
        output_path = os.path.join(UPLOAD_FOLDER, 'updated_excel.xlsx')
        workbook.save(output_path)
        
        return jsonify({
            'success': f'Successfully updated {updated_count} rows in Excel file',
            'download_path': '/download-excel'
        })
        
    except ImportError:
        return jsonify({'error': 'Please install openpyxl: pip install openpyxl'}), 500
    except Exception as e:
        return jsonify({'error': f'Error processing Excel file: {str(e)}'}), 500

@app.route('/download-excel')
def download_excel():
    from flask import send_file
    
    output_path = os.path.join(UPLOAD_FOLDER, 'updated_excel.xlsx')
    if os.path.exists(output_path):
        return send_file(output_path, as_attachment=True, download_name='updated_excel.xlsx')
    else:
        return jsonify({'error': 'Updated Excel file not found'}), 404

@app.route('/generate-jsonl', methods=['POST'])
def generate_jsonl():
    try:
        import pandas as pd
        
        # Get data from request
        system_prompt = request.json.get('system_prompt', '')
        excel_path = os.path.join(UPLOAD_FOLDER, 'uploaded_excel.xlsx')
        
        if not os.path.exists(excel_path):
            return jsonify({'error': 'Please upload an Excel file first using the upload section above'}), 400
        
        if not system_prompt:
            return jsonify({'error': 'Please provide system prompt'}), 400
        
        # Load the Excel file
        df = pd.read_excel(excel_path)
        
        # Debug: Print available columns
        print(f"Available columns: {list(df.columns)}")
        print(f"DataFrame shape: {df.shape}")
        
        # Column mapping from Excel headers to JSON fields
        column_mapping = {
            'Filename': 'img_name',
            'NIK': 'NIK',
            'NomorKK': 'NoKK',
            'NamaLengkap': 'NamaLengkap',
            'JenisKelamin': 'JenisKelamin',
            'TempatLahir': 'TempatLahir',
            'TanggalLahir': 'TanggalLahir',
            'Alamat': 'Alamat',
            'JenisPekerjaan': 'JenisPekerjaan',
            'Agama': 'Agama',
            'GolonganDarah': 'GolonganDarah',
            'StatusHubunganDalamKeluarga': 'StatusHubunganDalamKeluarga',
            'StatusPerkawinan': 'StatusPerkawinan',
            'Ayah': 'Ayah',
            'Ibu': 'Ibu',
            'Pendidikan': 'Pendidikan',
            'RT': 'RT',
            'RW': 'RW',
            'Desa/Kelurahan': 'DesaKelurahan',
            'Kecamatan': 'Kecamatan',
            'KabupatenKota': 'KabupatenKota',
            'Provinsi': 'Provinsi',
            'Kewarganegaraan': 'Kewarganegaraan'
        }
        
        jsonl_lines = []
        
        # Group by filename to get all family members from the same card
        # Then get the raw text for that filename
        filename_groups = {}
        
        for index, row in df.iterrows():
            filename = str(row.get('Filename', '')).strip()
            if not filename or filename == 'nan':
                continue
                
            if filename not in filename_groups:
                filename_groups[filename] = {
                    'raw_text': '',
                    'members': []
                }
            
            # Get the raw OCR text from column BY (only need to get it once per filename)
            if not filename_groups[filename]['raw_text']:
                raw_text = ""
                
                # Try different ways to get the raw text
                if 'RAW DATA' in df.columns:
                    raw_text = str(row['RAW DATA']) if pd.notna(row['RAW DATA']) else ""
                elif len(df.columns) > 76:  # Column BY is index 76 (0-based)
                    raw_text = str(df.iloc[index, 76]) if pd.notna(df.iloc[index, 76]) else ""
                else:
                    # Try to find a column that might contain raw text
                    for col in df.columns:
                        if 'raw' in str(col).lower() or 'text' in str(col).lower():
                            raw_text = str(row[col]) if pd.notna(row[col]) else ""
                            break
                
                filename_groups[filename]['raw_text'] = raw_text
                
            # Create member data
            member = {}
            
            # Map Excel columns to JSON fields
            for excel_col, json_field in column_mapping.items():
                if excel_col in df.columns:
                    value = row[excel_col]

                    # Handle special formatting
                    if json_field == 'RT' and pd.notna(value):
                        member[json_field] = f"{int(value):03d}"  # 3 digits
                    elif json_field == 'RW' and pd.notna(value):
                        member[json_field] = f"{int(value):02d}"  # 2 digits
                    elif json_field in ['TanggalLahir', 'KKDisahkanTanggal'] and pd.notna(value):
                        # Convert to yyyy-mm-dd format if needed
                        try:
                            if isinstance(value, str):
                                member[json_field] = value
                            else:
                                member[json_field] = value.strftime('%Y-%m-%d')
                        except:
                            member[json_field] = str(value) if pd.notna(value) else ""
                    elif pd.notna(value):
                        # Remove quotes for numeric ID fields if possible
                        if json_field in ['NIK', 'NoKK']:
                            # Remove Excel-style leading apostrophe (') or any single quotes
                            s = str(value)
                            # Remove all single quote characters but preserve other characters
                            s = s.replace("'", "").strip()
                            member[json_field] = s
                        else:
                            member[json_field] = str(value)
                    else:
                        member[json_field] = "" if json_field not in ['NoPaspor', 'NoKITAP'] else None
            
            # Add missing fields with default values
            if 'KodePos' not in member:
                member['KodePos'] = ""
            if 'KKDisahkanTanggal' not in member:
                member['KKDisahkanTanggal'] = ""
            if 'NoPaspor' not in member:
                member['NoPaspor'] = None
            if 'NoKITAP' not in member:
                member['NoKITAP'] = None
            
            filename_groups[filename]['members'].append(member)
        
        # Process each filename group to create JSONL entries
        for filename, group_data in filename_groups.items():
            raw_text = group_data['raw_text']
            members = group_data['members']
            
            # Skip if no raw text or no members
            if not raw_text or raw_text == "nan" or not members:
                continue
            
            # Find head of family to set NamaKepalaKeluarga for all members
            head_of_family = ""
            for member in members:
                status = member.get('StatusHubunganDalamKeluarga', '').upper()
                if 'KEPALA' in status:
                    head_of_family = member.get('NamaLengkap', '')
                    break
            
            # Set NamaKepalaKeluarga for all members
            for member in members:
                if 'NamaKepalaKeluarga' not in member or not member['NamaKepalaKeluarga']:
                    member['NamaKepalaKeluarga'] = head_of_family or member.get('NamaLengkap', '')
            
            # Create the assistant response JSON with all family members
            assistant_response = {
                "isKK": True,
                "AnggotaKeluarga": members
            }
            
            # Create JSONL entry using raw OCR text as user prompt
            jsonl_entry = {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": raw_text},
                    {"role": "assistant", "content": json.dumps(assistant_response, ensure_ascii=False)}
                ]
            }
            
            jsonl_lines.append(json.dumps(jsonl_entry, ensure_ascii=False))
        
        # Save JSONL file
        output_path = os.path.join(UPLOAD_FOLDER, 'finetuning_data.jsonl')
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(jsonl_lines))
        
        return jsonify({
            'success': f'Successfully generated {len(jsonl_lines)} JSONL entries',
            'download_path': '/download-jsonl',
            'preview': jsonl_lines[0] if jsonl_lines else None
        })
        
    except ImportError:
        return jsonify({'error': 'Please install pandas: pip install pandas'}), 500
    except Exception as e:
        return jsonify({'error': f'Error generating JSONL: {str(e)}'}), 500

@app.route('/download-jsonl')
def download_jsonl():
    from flask import send_file
    
    output_path = os.path.join(UPLOAD_FOLDER, 'finetuning_data.jsonl')
    if os.path.exists(output_path):
        return send_file(output_path, as_attachment=True, download_name='finetuning_data.jsonl')
    else:
        return jsonify({'error': 'JSONL file not found'}), 404

@app.route('/api/ocr', methods=['POST'])
def api_ocr():
    """
    API endpoint for OCR-only functionality
    Accepts an image file and returns OCR text without preprocessing
    """
    try:
        # Check if image file is in request
        if 'image' not in request.files:
            return jsonify({'error': 'No image file provided'}), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': 'No image file selected'}), 400
        
        # Check if file is an image
        if not file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff')):
            return jsonify({'error': 'Invalid image format. Supported formats: PNG, JPG, JPEG, GIF, BMP, TIFF'}), 400
        
        # Save the uploaded file temporarily
        temp_filename = f"temp_ocr_{int(time.time())}_{file.filename}"
        temp_filepath = os.path.join(UPLOAD_FOLDER, temp_filename)
        file.save(temp_filepath)
        
        try:
            # Extract text without preprocessing
            extracted_text = extract_text_vision_raw(temp_filepath)
            
            # Clean up temporary file
            os.remove(temp_filepath)
            
            return jsonify({
                'success': True,
                'filename': file.filename,
                'text': extracted_text,
                'message': 'OCR completed successfully'
            })
            
        except Exception as ocr_error:
            # Clean up temporary file in case of error
            if os.path.exists(temp_filepath):
                os.remove(temp_filepath)
            return jsonify({'error': f'OCR processing failed: {str(ocr_error)}'}), 500
            
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host="0.0.0.0",port=5001, debug=True)
