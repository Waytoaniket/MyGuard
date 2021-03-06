import boto3
import botocore
import csv
import os
import re
import shutil
import time
import datetime
import base64
from dotenv import load_dotenv
from flask import Blueprint, current_app, render_template, url_for, redirect, request, session, flash
from werkzeug.utils import secure_filename
from ..extensions import mongo
# from bson.json_util import dumps
# from bson.objectid import ObjectId
import json

enter = Blueprint("enter",  __name__, static_folder="images", template_folder="templates")

'''
Status codes:
0 - Invalid Temperature
1 - User Not Found
2 - Face Not Recognized
3 - All Details Verified
'''

@enter.route("/")
def enter_details():
    return render_template("enter_details.html")

@enter.route("/form-result", methods=['POST','GET'])
def enter_form_details():
    if request.method == 'POST':
        user_id = request.form['id']
        _type = request.form['type']
        temp = request.form['temp']
        timestamp = datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S')

        # DB connection
        records_collection = mongo.db.records
        find_user = list(mongo.db.users.find({"mg_id":user_id}))
        if len(find_user) == 0:
                name = None
        else:
            for x in find_user:
                name = x['name']

        # 0 - Invalid Entry
        record_entry = {
                "mg_id": user_id,
                "name": name,
                "temperature": temp,
                "type": _type,
                "timestamp": timestamp,
                "status": "",
                "status_code": None 
            }

        if float(temp) > 97 and float(temp) < 99.5:
            temp_validity = True
        else:
            temp_validity = False
            # 0 - Invalid Temperature
            record_entry['status'] = "Denied: Invalid Temperature"
            record_entry['status_code'] = 0
            records_collection.insert_one(record_entry)
        
        if 'file' not in request.files:
            flash('No image found')
        file = request.files['image']
        
        if file.filename == '':
            flash('No image selected')
        else:
            image = request.files['image']  
            image_string = base64.b64encode(image.read())
            image_string = image_string.decode('utf-8')
        print(file)
        if file and temp_validity:
            
            load_dotenv()
            image = str(user_id)+"_upload"+".jpg"
            
            # Check if ID exists
            s3 = boto3.resource('s3',
                            aws_access_key_id = os.environ["ACCESS_KEY_ID"],
                            aws_secret_access_key = os.environ["SECRET_ACCESS_KEY"],
                            region_name='us-east-2')
            try:
                s3.Object('my-guard-bucket', str(user_id+".jpg")).load()
            except botocore.exceptions.ClientError as e:
                if e.response['Error']['Code'] == "404":
                    # The object does not exist.
                    IDExists = False

                else:
                    # Something else has gone wrong.            
                    raise e
            else:
                # The object does exist.
                IDExists = True

            # Facial Recognition
            if IDExists:
                # filename = secure_filename(str(user_id)+"_upload"+".jpg")
                # if(not os.path.exists(current_app.config['ENTER_IMAGES_FOLDER'])):
                #     print(current_app.config['ENTER_IMAGES_FOLDER'])
                #     os.makedirs(current_app.config['ENTER_IMAGES_FOLDER'])
                # file.save(os.path.join(current_app.config['ENTER_IMAGES_FOLDER'], filename))

                client = boto3.client('rekognition',
                                        aws_access_key_id = os.environ["ACCESS_KEY_ID"],
                                        aws_secret_access_key = os.environ["SECRET_ACCESS_KEY"],
                                        region_name='us-east-2')
                file.seek(0)
                source_bytes = file.read()

                compare_img = str(user_id+".jpg")
                response = client.compare_faces(
                    SourceImage={
                        'Bytes': source_bytes
                    },
                    TargetImage={
                        'S3Object': {
                            'Bucket': 'my-guard-bucket',
                            'Name': compare_img
                        }
                    }
                )

                for key, value in response.items():
                    if key in ('FaceMatches'):
                        if len(value) == 0:
                            Recognition = False

                        for att in value:
                            if att['Similarity'] > 95:
                                Recognition = True
                                # 3 - Success
                                record_entry['status'] = "Allowed: All Details Verified"
                                record_entry['status_code'] = 3
                                records_collection.insert_one(record_entry)
                            else:
                                Recognition = False 

                        if not Recognition:
                            # 2 - Face not recognized
                            record_entry['status'] = "Denied: Face Not Recognized"
                            record_entry['status_code'] = 2
                            records_collection.insert_one(record_entry)   
            else:
                Recognition = False
                # 1 - User not found 
                record_entry['status'] = "Denied: User Not Found"
                record_entry['status_code'] = 1
                records_collection.insert_one(record_entry)
        
        else:
            IDExists = False
            Recognition = False
            timestamp = None
        

        result = request.form

        return render_template( "enter_form-result.html",
                                result = result, 
                                file=image_string, 
                                user_id=user_id, 
                                temp=temp, 
                                type=_type,
                                temp_validity=temp_validity,
                                IDExists=IDExists, 
                                Recognition=Recognition, 
                                timestamp=timestamp)

@enter.route("/records")
def users():
    # Mongo DB Atlas - Records
    results = mongo.db.records.find({})
    return render_template("records.html", results=results)

@enter.route("/stats")
def stats():
    # Mongo DB Atlas - Records
    records = mongo.db.records.find()

    # Statistics
    '''Count of Users'''
    total_users = mongo.db.users.find({}).count()

    '''Count of Logs'''
    total_logs = mongo.db.records.find({}).count()

    '''In/Out'''
    entry_type = [
        mongo.db.records.find({"type": "IN"}).count(),
        mongo.db.records.find({"type": "OUT"}).count()
    ]

    ''' 0,1,2,3 ''' 
    status_code = []
    for code in range(4):
        code_records = mongo.db.records.find({"status_code": code})
        status_code.append(code_records.count())

    response = []
    for record in records:
        record['_id'] = str(record['_id'])
        response.append(record)

    return render_template("stats.html", 
                                records_json=json.dumps(response),
                                 status_code=status_code, 
                                 entry_type=entry_type,
                                 total_logs=total_logs,
                                 total_users=total_users
                        )