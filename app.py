from flask import Flask, request, render_template, redirect, url_for, flash, send_file
import requests
import openai
import os
import PyPDF2
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
import textwrap

app = Flask(__name__)
app.secret_key = "supersecretkey"

# Ensure the uploads directory exists
if not os.path.exists('uploads'):
    os.makedirs('uploads')  # Create the uploads directory if it does not exist

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        file = request.files["file"]
        if file:
            file_path = os.path.join("uploads", file.filename)
            file.save(file_path)
            openai_key = request.form["openai_key"]  
            source_language = request.form["source_language"]  
            target_language = request.form["target_language"]  
            selected_model = request.form["gpt_model"]

            ocr_text = ocr_pdf(file_path, source_language)
            translated_text = translate_text(openai_key, ocr_text, target_language, selected_model)
            return render_template("result.html", translated_text=translated_text, filename=file.filename)
    return render_template("index.html")

@app.route("/download_pdf", methods=["POST"])
def download_pdf():
    translated_text = request.form["translated_text"]
    filename = request.form["filename"]
    pdf_buffer = generate_pdf(translated_text, filename)
    return send_file(pdf_buffer, as_attachment=True, download_name="translated_text.pdf", mimetype='application/pdf')


def ocr_pdf(file_path, language):
    url = "https://api.ocr.space/parse/image"

    # https://ocr.space/OCRAPI
    headers = {
        'apikey': 'helloworld'
    }
    data = {
        'language': language,
        'scale': 'true',
    }
    
    def send_request(pdf_chunk):
        with open('temp.pdf', 'wb') as temp_file:
            pdf_chunk.write(temp_file)
        with open('temp.pdf', 'rb') as temp_file:
            files = {
                'file': temp_file,
            }
            response = requests.post(url, headers=headers, files=files, data=data)
            return response.json()

    inputFile = open(file_path, 'rb')
    pdfReader = PyPDF2.PdfReader(inputFile)
    numPages = len(pdfReader.pages)

    all_parsed_text = []
    
    # Define page groups to process
    pages = list(range(numPages))
    while pages:
        if len(pages) >= 3:
            group = pages[:3]
            pages = pages[3:]
        else:
            group = pages
            pages = []
        
        pdf_writer = PyPDF2.PdfWriter()
        for page_number in group:
            pdf_writer.add_page(pdfReader.pages[page_number])
        
        result = send_request(pdf_writer)
        try:
            parsed_texts = [result["ParsedResults"][i]["ParsedText"] for i in range(len(result["ParsedResults"]))]
            all_parsed_text.extend(parsed_texts)
        except KeyError as e:
            print(f"Key error: {e}")
    
    return "\n".join(all_parsed_text)


def translate_text(api_key, text, target_language, model):
    if not text.strip():
        return "No text extracted"
    
    # Define chunk size
    chunk_size = 3000  # Adjust as necessary to fit within token limits

    openai.api_key = api_key
    translated_text = []

    # Split the text into chunks
    for i in range(0, len(text), chunk_size):
        text_chunk = text[i:i+chunk_size]
        response = openai.chat.completions.create(
            model = model,
            messages=[
                {"role": "system", "content": f"Translate the following text to {target_language} as accurately as possible, (keep all metaphors as well): {text_chunk}"},
                {"role": "user", "content": text_chunk}
            ]
        )
        translated_text.append(response.choices[0].message.content)
    
    # Join all translated chunks into a single string
    return "\n".join(translated_text)

def generate_pdf(text, filename):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    pdfmetrics.registerFont(TTFont('DejaVuSans', 'DejaVuSans.ttf'))
    c.setFont("DejaVuSans", 12)
    width, height = letter

    margin = 40
    max_width = width - 2 * margin
    max_height = height - 2 * margin

    c.setFont("DejaVuSans", 16)

    filename_width = pdfmetrics.stringWidth(f"{filename} Translated", "DejaVuSans", 16)

    c.drawString((width - filename_width) / 2, height - margin , f"{filename} Translated")
    c.setFont("DejaVuSans", 12)

    text_object = c.beginText(margin, height - 2 * margin)
    text_object.setLeading(18)

    lines = text.split('\n')
    wrapped_lines = []

    for line in lines:
        wrapped_lines.extend(textwrap.wrap(line, width=max_width / 7))

    for line in wrapped_lines:
        if text_object.getY() <= margin:
            c.drawText(text_object)
            c.showPage()
            text_object = c.beginText(margin, height - margin)
            text_object.setLeading(18)
            text_object.setFont("DejaVuSans", 12)
        text_object.textLine(line)

    c.drawText(text_object)
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer


if __name__ == '__main__':
    app.run(debug=True)
