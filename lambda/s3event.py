import boto3
import logging
import time

# Configure logging
LOG = logging.getLogger()
LOG.setLevel(logging.INFO)  # Set to DEBUG level for detailed logging

def move_to_bucket(bucket_name, object_key, s3):
    destination_key = f"valid-docs-folder/{object_key}"
    destination_bucket = 'valid-docs-bucket'

    try:
        s3.copy_object(
            Bucket=destination_bucket,
            CopySource={'Bucket': bucket_name, 'Key': object_key},
            Key=destination_key
        )
        LOG.info(f"File copied to S3 bucket: {destination_bucket}/{destination_key}")

        # Delete the original object from the source bucket
        s3.delete_object(
            Bucket=bucket_name,
            Key=object_key
        )
        LOG.info(f"Original object deleted from S3 bucket: {bucket_name}/{object_key}")
    except Exception as e:
        LOG.error(f"Error moving to valid docs bucket: {str(e)}")

def process_comprehend(text):
    comprehend_client = boto3.client('comprehend')

    # Detect PII entities in the text
    pii_entities_response = comprehend_client.contains_pii_entities(Text=text, LanguageCode='en')
    entities = []

    if 'Labels' in pii_entities_response:
        for label in pii_entities_response['Labels']:
            if label['Score'] > 0.7:  # Check if the score is greater than 70
                pii_entity = {
                    "Name": label['Name'],
                    "Score": label['Score']
                }
                entities.append(pii_entity)

    return entities

def move_to_valid_passport_bucket(bucket_name, object_key, s3):
    destination_key = f"valid-docs-folder/passport/{object_key}"
    destination_bucket = 'valid-docs-bucket'
    try:
        s3.copy_object(
            Bucket=destination_bucket,
            CopySource={'Bucket': bucket_name, 'Key': object_key},
            Key=destination_key
        )
        LOG.info(f"File copied to S3 bucket: {destination_bucket}/{destination_key}")

        # Delete the original object from the source bucket
        s3.delete_object(
            Bucket=bucket_name,
            Key=object_key
        )
        LOG.info(f"Original object deleted from S3 bucket: {bucket_name}/{object_key}")

    except Exception as e:
        LOG.error(f"Error moving passport to valid docs bucket: {str(e)}")

def process_image_with_rekognition(image_bytes):
    rekognition = boto3.client('rekognition')
    labels = []

    try:
        rekognition_response = rekognition.detect_labels(
            Image={
                'Bytes': image_bytes
            }
        )
        
        # Wait and check the status
        while 'JobStatus' in rekognition_response and rekognition_response['JobStatus'] == 'IN_PROGRESS':
            time.sleep(5)  # Wait for 5 seconds before checking again
            rekognition_response = rekognition.get_label_detection(JobId=rekognition_response['JobId'])
        
        if 'Labels' in rekognition_response:
            labels = rekognition_response['Labels']
        
        return labels
        
    except Exception as e:
        LOG.error(f"Error processing image with Rekognition: {str(e)}")
        return labels

def get_textract_results(job_id):
    textract_client = boto3.client('textract')

    while True:
        response = textract_client.get_document_text_detection(JobId=job_id)
        status = response['JobStatus']
        
        if status == 'SUCCEEDED':
            return response
        elif status == 'FAILED':
            raise Exception("Textract job failed")
        
        time.sleep(5)  # Wait for 5 seconds before checking again
        
def move_to_invalid_bucket(bucket_name, object_key, s3):
    destination_key = f"invalid-docs-folder/{object_key}"
    destination_bucket = 'invalid-docs-bucket'
    try:
        s3.copy_object(
            Bucket=destination_bucket,
            CopySource={'Bucket': bucket_name, 'Key': object_key},
            Key=destination_key
        )
        LOG.info(f"File copied to S3 bucket: {destination_bucket}/{destination_key}")

        # Delete the original object from docs-landing-bucket
        s3.delete_object(
            Bucket=bucket_name,
            Key=object_key
        )
        LOG.info(f"Original object deleted from S3 bucket: {bucket_name}/{object_key}")

    except Exception as e:
        LOG.error(f"Error copying or deleting file: {str(e)}")

def process_pii_offsets(text):
    comprehend_client = boto3.client('comprehend')

    # Detect PII entities in the text using PII offsets
    pii_entities_response = comprehend_client.detect_pii_entities(Text=text, LanguageCode='en')
    entities = [] 

    if 'Entities' in pii_entities_response:
        for entity in pii_entities_response['Entities']:            
                pii_entity = {
                    "Type": entity['Type'],
                    "Score": entity['Score'],
                    "BeginOffset": entity['BeginOffset'],
                    "EndOffset": entity['EndOffset']
                }
                entities.append(pii_entity)
    return entities

def process_pii_labels(text):
    comprehend_client = boto3.client('comprehend')

    try:
        # Detect PII entities in the text using Comprehend
        pii_entities_response = comprehend_client.contains_pii_entities(Text=text, LanguageCode='en')
        entities = []        

        if 'Labels' in pii_entities_response:
            for label in pii_entities_response['Labels']:                    
                    pii_entity = {
                        "Name": label['Name'],
                        "Score": label['Score']
                    }
                    entities.append(pii_entity)

        return entities

    except Exception as e:
        print(f"Error processing PII labels with Comprehend: {str(e)}")
        return []
            
def lambda_handler(event, context):    
    # Define the S3 bucket names
    DOCS_LANDING_BUCKET = 'docs-landing-bucket'
    VALID_DOCS_BUCKET = 'valid-docs-bucket'
    INVALID_DOCS_BUCKET = 'invalid-docs-bucket'

    # Define the S3 client
    s3 = boto3.client('s3')

    # Extract S3 bucket, key, and file name from the incoming event
    records = event.get('Records', [])
    if not records:
        LOG.error("No records found in the event.")
        return {
            "error_message": "No records found in the event"
        }

    for record in records:
        s3_info = record.get('s3', {})
        bucket_name = s3_info.get('bucket', {}).get('name')
        object_key = s3_info.get('object', {}).get('key')

        LOG.info(f"File name is {object_key}")

        # Check if the object is an image (jpg or png)
        if object_key.lower().endswith(('.jpg', '.jpeg', '.png')):
            LOG.info(f"Processing image: {object_key}")
            try:
                LOG.info("Starting Rekognition:")
                response = s3.get_object(Bucket=bucket_name, Key=object_key)
                image_bytes = response['Body'].read()
                
                # Call the method to process the image with Rekognition
                rekognition_labels = process_image_with_rekognition(image_bytes)

                LOG.info("Detected Rekognition labels:")
                valid_labels = ['Text', 'Person', 'Face', 'Head', 'QR Code', 'Document', 'Id Cards','Passport']
                min_confidence = 50.0  # Minimum confidence threshold in percentage

                # Set a default destination_bucket value
                destination_bucket = 'invalid-docs-bucket'
                destination_key = f"invalid-docs-folder/{object_key}"

                valid_label_found = False
                for label in rekognition_labels:
                    if label['Name'] in valid_labels and label['Confidence'] >= min_confidence:
                        LOG.info(f"Label: {label['Name']}, Confidence: {label['Confidence']}")
                        valid_label_found = True

                    if label['Name'] == 'Passport' and label['Confidence'] >= 90:
                        LOG.info("Found 'Passport' with high confidence. Valid Govt ID.")
                        print("Found 'Passport' with high confidence. Valid Govt ID.")

                        # Move the document to the valid-docs-bucket under passport folder
                        move_to_valid_passport_bucket(bucket_name, object_key, s3)
                        break    
                
                if valid_label_found and not (valid_label_found and label['Name'] == 'Passport' and label['Confidence'] >= 90):
                    # Call Amazon Textract
                    LOG.info("Valid Labels found, calling Textract")
                    textract_client = boto3.client('textract')
                    response = None  # Initialize response with a default value

                    try:
                        response = textract_client.start_document_text_detection(
                            DocumentLocation={"S3Object": {"Bucket": bucket_name, "Name": object_key}}
                        )
                        job_id = response['JobId']
                        LOG.info(f"Textract job started with JobId: {job_id}")
                    except textract_client.exceptions.UnsupportedDocumentException as e:
                        LOG.error(f"Error copying or deleting file: {str(e)}")

                        move_to_invalid_bucket(bucket_name, object_key, s3)
                        return {
                            "error_message": "Unsupported document format"
                        }
                    except textract_client.exceptions.InvalidS3ObjectException as e:
                        LOG.error(f"Unsupported Format/Object type detected. Textract can't process the File. Please try with a new file: {str(e)}")
                        
                        #LOG.info(f"Moving the file to invalid-docs")
                        # Move the file to the invalid-docs-bucket
                        move_to_invalid_bucket(bucket_name, object_key, s3)
                        return {
                            "error_message": "Invalid S3 object for textract"
                        }

                    if response is not None:
                        # Wait for Textract job to complete and get results
                        textract_results = get_textract_results(job_id)
                        
                        # Extract text blocks from Textract results
                        blocks = textract_results["Blocks"]
                        text_blocks = [block for block in blocks if block["BlockType"] == "LINE"]

                        # Extract text from text blocks
                        text = ' '.join([block["Text"] for block in text_blocks])

                        LOG.info("Extracted Textract Text passing to Comprehend %s", text)
                        # Process extracted text using Amazon Comprehend
                        comprehend_results = process_comprehend(text)

                        try:
                             LOG.info("Extracted Textract Text passing to check Driving License: %s", text)
                             # Process extracted text using Amazon Comprehend

                             words = text.split()
                             print("Individual words in the text:")
                             for word in words:
                                  print(word)                             

                             if "Driving" in words and "Licence" in words:
                                 LOG.info("Found 'Driving License' text. Using Comprehend PII offset analysis.")
                                 comprehend_results = process_pii_offsets(text)
                                 print("Comprehend results:", comprehend_results)

                             elif "Aadhaar" in words:
                                 LOG.info("Found 'Aadhaar' text. Using Comprehend PII label analysis.")
                                 comprehend_results = process_pii_labels(text)
                                 print("Comprehend results:", comprehend_results)

                             elif "Permanent" in words and "Account" in words and "Number" in words:
                                 LOG.info("Found 'PAN' text. Using Comprehend PII label analysis.")
                                 comprehend_results = process_pii_offsets(text)
                                 print("Comprehend results:", comprehend_results)     

                        except Exception as comprehend_error:
                             LOG.error(f"Error while processing text with Comprehend: {str(comprehend_error)}")
                             comprehend_results = []  # Set an empty result or handle the error as needed
                             print("Error processing text with Comprehend:", comprehend_error)                                             

                        # Check if any of the specified entities are identified in comprehend_results
                        specified_entity_types = ['IN_AADHAAR', 'IN_PERMANENT_ACCOUNT_NUMBER', 'DRIVER_ID', 'PASSPORT_NUMBER']

                        found_entity = False
                        for entity in comprehend_results:
                             if entity.get('Name') == 'IN_AADHAAR' or entity.get('Type') == 'DRIVER_ID' or entity.get('Type') == 'IN_PERMANENT_ACCOUNT_NUMBER':
                                  LOG.info("Document is a valid Govt ID or it contains Govt ID data.")
                                  print("Document is a valid Govt ID or it contains Govt ID data.")
                                  found_entity = True
                                  # Move the document to the valid-docs-bucket under passport folder
                                  move_to_bucket(bucket_name, object_key, s3)
                                  break
                             if not found_entity:
                                  LOG.info("No Valid Entity Type found.")
                                  print("No Valid Entity Type found.")
                                  # Move the file to the invalid-docs-bucket
                                  move_to_invalid_bucket(bucket_name, object_key, s3)
    
                                  # Delete the original object from docs-landing-bucket
                                  s3.delete_object(Bucket=bucket_name, Key=object_key)                    
                            
                    else:
                        LOG.info("Document is not a valid Govt ID. Skipping processing.")
                        print("Document is not a valid Govt ID. Skipping processing.")                       
                        # Move the file to the invalid-docs-bucket
                        move_to_invalid_bucket(bucket_name, object_key, s3)
    
                        # Delete the original object from docs-landing-bucket
                        s3.delete_object(Bucket=bucket_name, Key=object_key)
        

            except Exception as e:
                LOG.error(f"Document is not a valid jpg, png or jpeg format: {str(e)}")
                # Move the file to the invalid-docs-bucket
                move_to_invalid_bucket(bucket_name, object_key, s3)
    
                # Delete the original object from docs-landing-bucket
                s3.delete_object(Bucket=bucket_name, Key=object_key)
        else:
            LOG.info("Document is not in desired format. Skipping processing.")
            print("Document is not in desired format. Skipping processing.")                       
            
            # Move the file to the invalid-docs-bucket
            move_to_invalid_bucket(bucket_name, object_key, s3)
    
            # Delete the original object from docs-landing-bucket
            s3.delete_object(Bucket=bucket_name, Key=object_key)
