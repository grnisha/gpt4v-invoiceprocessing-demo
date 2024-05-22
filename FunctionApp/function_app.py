import azure.functions as func
import logging
import json
import os
import io
import base64
from pdf2image import convert_from_path
from urllib.parse import urlparse, unquote
from azure.storage.blob import BlobServiceClient
import tempfile
from azure.identity import DefaultAzureCredential
import time
import requests
from mimetypes import guess_type
from jinja2 import Environment, FileSystemLoader

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@app.function_name(name="PDFProcessor")
@app.route(route="pdfprocessor", methods=["POST"])
def pdf_processor(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    try:
        req_body = req.get_json()

        # Get the file name from the blob URL
        url_path = urlparse(req_body.get('blob_url')).path
        # Decode the URL-encoded file name
        file_name_with_ext = unquote(os.path.basename(url_path))
        # Split the file name and the extension
        file_name, file_extension = os.path.splitext(file_name_with_ext)

        # Initialize blob client
        credential = DefaultAzureCredential()
        blob_service_client = BlobServiceClient(account_url=os.getenv('BLOB_CONNECTION_SETTING'), credential=credential)
        container_name = os.getenv('BLOB_CONTAINER_NAME')

       # Get the blob client for the PDF file
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=url_path)

        pdf_path = ''
        # Create a temporary file
        with tempfile.NamedTemporaryFile(delete=False) as f:
            pdf_path = f.name

        # Download the PDF file to the temporary file
        with open(pdf_path, "wb") as download_file:
            download_file.write(blob_client.download_blob().readall())

        
        # get the pdf file from the blob storage
        images = convert_from_path(pdf_path)

        # After processing, delete the temporary file
        os.remove(pdf_path)
                    
        # Initialize an empty list to hold the response data
        response_data = []

        # save images as png files in blob storage
        for i, image in enumerate(images):
            image_path = f"{i}_{file_name}.png"
            image.save(image_path, "PNG")
            blob_name = f"{file_name}/{i}_{file_name}.png"
            # add output bindings for blob storage
            blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
            
            # Add blob url to the response data
            response_data.append({"file": blob_name})

            # Upload the created image to the blob storage
            with open(f"{i}_{file_name}.png", "rb") as data:
                blob_client.upload_blob(data, overwrite=True)
            
            # After uploading, delete the image file
            os.remove(image_path)

        
        #convert blob_list to json
        res = json.dumps(response_data)

        # return the images
        return func.HttpResponse(res, status_code=200)
    except Exception as e:
        return func.HttpResponse(f"Error: {str(e)}", status_code=500)
        

@app.function_name(name="ProcessInvoice")
@app.route(route="processinvoice", methods=["POST"])
def process_invoice(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    try:
        req_body = req.get_json()
       
        # Get image data
        img_data = get_image_list(req_body)
        
        # Get invoice
        invoice = process_invoice(img_data)

        res = json.dumps(invoice)

        # Return the invoice
        return func.HttpResponse(res, status_code=200) 
        
    except Exception as e:
        return func.HttpResponse(f"Error: {str(e)}", status_code=500)
    

# Get images from blob and format it for API call
def get_image_list(req_body):
    # Initialize blob client
    credential = DefaultAzureCredential()
    blob_service_client = BlobServiceClient(account_url=os.getenv('BLOB_CONNECTION_SETTING'), credential=credential)
    container_name = os.getenv('BLOB_CONTAINER_NAME')
            
    # Initialize image list
    img_list =[]
    # Set default mime type
    mime_type = 'application/octet-stream'

    #For each blob url in req_body, get the png file from azure blob storage and base64 encode
    for item in req_body:
        image = item['file']
        #Download from blob storage
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=image)
        stream = io.BytesIO()
        blob_data = blob_client.download_blob().readall()
        stream.write(blob_data)
        stream.seek(0)
        base64_encoded = base64.b64encode(stream.read()).decode('utf-8')
        # Guess the MIME type of the image based on the file extension
        mime_type, _ = guess_type(image)
        image_url_section = { 
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime_type};base64,{base64_encoded}"
                }
            }
                
        img_list.append(image_url_section)
            
    return img_list

# Process Invoice with rest call
def process_invoice(img_list):
    env = Environment(loader=FileSystemLoader('.'))
    template = env.get_template('prompt.j2')
    prompt = template.render()
    aoai_api_url = f"{os.getenv('AOAI_ENDPOINT')}openai/deployments/{os.getenv('AOAI_DEPLOYMENT_NAME')}/extensions/chat/completions?api-version={os.getenv('AOAI_API_VERSION')}"
    # Base messages list
    messages = [
        { "role": "system", "content": prompt },
        { "role": "user", "content": [  
            { 
                "type": "text", 
                "text": "Please extarct relevant fileds from the invoice"
            }
        ] } 
    ]

    #For each file get the image url and add image_url section to the base message
    for img in img_list:
        # Add image url to the message
        messages[1]['content'].append(img)

    # Define the data sources
    data_sources = [
        {
            "type": "AzureComputerVision",
            "parameters": {
                "endpoint": os.getenv('AI_VISION_ENDPOINT'),
                "key": os.getenv('AI_VISION_KEY')
            }
        }
    ]

    # Define the enhancements
    enhancements = {
        "ocr": {
            "enabled": True
        }
    }

    payload = json.dumps({
        "enhancements": enhancements,
        "dataSources":data_sources,
        "messages": messages,
        "max_tokens": 4000,
        "temperature": 0
    })
    headers = {
    'api-key': os.getenv('AOAI_KEY'),
    'Content-Type': 'application/json'
    }

    while True:
        response = requests.request("POST",aoai_api_url, headers=headers, data=payload)
        if response.status_code != 429:
            break
        
        # Sleep for 5 seconds before retrying in case of 429 error.
        time.sleep(5)   
    
    # Convert the response to a dictionary
    response_dict = json.loads(response.text)


    # Extract the 'choices' field which contains the model's responses
    choices = response_dict.get('choices')

    # Get the text of the first response
    response_text = choices[0].get('message').get('content') if choices else None
    
    response_text=response_text.replace("```json\n", "").replace("\n```", "")

    # Load the JSON string into a Python dictionary
    invoice_details = json.loads(response_text)

    return invoice_details