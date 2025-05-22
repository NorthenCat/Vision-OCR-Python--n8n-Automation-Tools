# KK-OCR Python Component

This repository contains the Python component of the KK-OCR project.

## Setup

### 1. Create a Virtual Environment

```bash
# Create a virtual environment
python -m venv venv
```

### 2. Activate the Virtual Environment

**macOS/Linux:**

```bash
source venv/bin/activate
```

**Windows (Command Prompt):**

```cmd
venv\Scripts\activate.bat
```

**Windows (PowerShell):**

```powershell
.\venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

## Usage

### Running the Application

```bash
python app.py
```

The application will start and be available at [http://localhost:5000](http://localhost:5000).

### Web Interface

1. Open your browser and navigate to [http://localhost:5000](http://localhost:5000)
2. Use the upload form to submit files for OCR processing

### Webhook Configuration for n8n

To integrate with n8n workflows:

1. Change the WEBHOOK_URL to your current WEBHOOK URL N8N

For n8n template, please contact: faldzddi@gmail.com

## License

MIT License

Copyright (c) 2023 KK-OCR

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
