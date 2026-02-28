from flask import Flask, render_template, request, jsonify, redirect, session, send_file
import uuid
import os
from dotenv import load_dotenv
import pandas as pd
from langchain_anthropic import ChatAnthropic
from langchain.chains import LLMChain
from langchain.chains.constitutional_ai.models import ConstitutionalPrinciple
from langchain.chains.constitutional_ai.base import ConstitutionalChain
from langchain_core.prompts import PromptTemplate
import pyrebase
from datetime import datetime
import hashlib
from pymongo import MongoClient
from langchain_mongodb import MongoDBAtlasVectorSearch
from langchain_openai import OpenAIEmbeddings
import pickle
from subprocess import Popen
from langchain_community.document_loaders import PDFMinerLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.chains.question_answering import load_qa_chain
import ast
from datetime import timedelta
import anthropic
import random
import ast
from flask import send_file, session, render_template
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
import os
import json


load_dotenv()

config = {
    "apiKey": "AIzaSyCylgLNzqWSRKfppga7ujIpBgv9GguAdSo",
    "authDomain": "career-coaching-4c0d4.firebaseapp.com",
    "databaseURL": "https://career-coaching-4c0d4-default-rtdb.firebaseio.com",
    "projectId": "career-coaching-4c0d4",
    "storageBucket": "career-coaching-4c0d4.appspot.com",
    "messagingSenderId": "294294975343",
    "appId": "1:294294975343:web:03850126ed507bbab66e9a",
    "measurementId": "G-BB1KVVM2NV"
}


firebase = pyrebase.initialize_app(config)
auth = firebase.auth()
db = firebase.database()

# For Claude
api_key = os.getenv("api_key", "")
model_name = os.getenv("model_name", "")
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', 'na')

llm = ChatAnthropic(temperature=0, anthropic_api_key=api_key, model_name=model_name)
llm2 = ChatAnthropic(temperature=0, anthropic_api_key=api_key, model_name="claude-3-5-haiku-20241022", max_tokens=8096)

#Gemini model
# if "GOOGLE_API_KEY" not in os.environ:
#     os.environ["GOOGLE_API_KEY"] = "AIzaSyD45cgmA-bnRFbQejgwHg7NwZNMqtEdvCM"

# llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro-001")

#OpenAI Embeddings


#Mongo DB Connection
ATLAS_CONNECTION_STRING = os.getenv('mongo_connection_string', 'na')

# Connect to your Atlas cluster
client = MongoClient(ATLAS_CONNECTION_STRING)

# Define collection and index name
db_name = "Career-Coaching"
collection_name = "data"
atlas_collection = client[db_name][collection_name]
vector_search_index = "vector_search"


vectorStore = MongoDBAtlasVectorSearch(
    atlas_collection, OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY), index_name=vector_search_index
)

retriever = vectorStore.as_retriever(
   search_type = "similarity",
   search_kwargs = {"k": 5, "score_threshold": 0.75}
)


def format_docs(docs):
   return "\n\n".join(doc.page_content for doc in docs)

app = Flask(__name__)

app.secret_key = os.getenv("secret_key", "")

# app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(seconds=15)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=3)

 # Secret salt (you should generate and keep this secret)
salt = os.getenv("salt_secret")

# Function to generate a consistent integer hash for an email
def generate_email_integer_hash(email):
    salted_email = salt + email
    sha256 = hashlib.sha256(salted_email.encode()).digest()
    # Take the lower 8 bits of the hash as an integer
    email_hash_8bit = int.from_bytes(sha256[-1:], byteorder='big')
    return email_hash_8bit


# Configure the upload folder
app.config['UPLOAD_FOLDER'] = 'uploads'

LIBRE_OFFICE = r"lowriter"

# Ensure the upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def convert_to_pdf(input_docx, out_folder):
        p = Popen([LIBRE_OFFICE, '--headless', '--convert-to', 'pdf', '--outdir',
                out_folder, input_docx])
        print([LIBRE_OFFICE, '--convert-to', 'pdf', input_docx])
        p.communicate() 


questions = {}
pdf_data = {}


@app.before_request
def make_session_permanent():
    session.permanent = True
    session.modified = True  


def vector_search(question):

    db_name = "Career-Coaching"
    collection_name = "career-advisory"
    atlas_collection = client[db_name][collection_name]
    vector_search_index = "advise"

    vectorStore = MongoDBAtlasVectorSearch(
        atlas_collection, OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY), index_name=vector_search_index
    )

    search_pipeline = [
        {
            "$search": {
                "index": "advise",  # The name of the search index in MongoDB Atlas
                "text": {
                    "query": question,  # The search term
                    "path": "subDomain",        # Search in the 'subDomain' field
                    "fuzzy": {
                        "maxEdits": 2,          # Allows up to 2 character changes (insertions, deletions, or substitutions)
                        "prefixLength": 0,      # No prefix length restriction
                        "maxExpansions": 1      # Limits the number of fuzzy matches that are expanded
                    }
                }
            }
        }
    ]

    # Step 4: Run the aggregation query
    results = atlas_collection.aggregate(search_pipeline)

    # Step 5: Retrieve the 'subDomain' field from the first search result
    first_result = next(results, None)  # Get the first result, or None if no results
    sub_domain_value = "*" #ensures the sub-domain values are universal if there is no match

    if first_result:
        sub_domain_value = first_result.get('subDomain')  # Extract the 'subDomain' field
        print(f"First result's subDomain: {sub_domain_value}")
    else:
        print("No results found.")
        sub_domain_value = "*"

    # Step 3: Define the $search aggregation query using the subDomain values


    search_pipeline = [
        {
            "$search": {
                "index": "advise",  # The name of the search index in MongoDB Atlas
                "compound": {
                    "should": [
                        {
                            "text": {
                                "query": "Career Advisor",  # First condition in compound query
                                "path": "domain"  # Search in the 'domain' field
                            }
                        },
                        {
                            "text": {
                                "query": sub_domain_value,  # Second condition
                                "path": "subDomain"  # Search in the 'value' field
                            }
                        },
                                            {
                            "text": {
                                "query": question,  # Third condition
                                "path": "value"  # Search in the 'value' field
                            }
                        }
                    ],
                    "minimumShouldMatch": 1  # At least one of the conditions must be satisfied
                }
            }
        }
    ]

    # Step 4: Run the aggregation query
    results = atlas_collection.aggregate(search_pipeline)

    RAG_Output = []

    # Step 5: Print the results
    for result in results:
        value = result.get('value')
        if value:
          RAG_Output.append(value)

        #print(result)
    return RAG_Output


def format_docs(RAG_Output):
    data = ". ".join(RAG_Output)
    return data

@app.get('/')
def resume_upload():
    if "user" in session:
        session_id = session["user"]
        user_name = session_id.split("@")[0]
        questions[session['user']] = {"education_status":[[]], "cand-details":[], "previous_chat":[]}


        try:
            resume_text = pdf_data[session_id]     
            return render_template("home.html", session_id=session_id, user_name=user_name)

        except:
            return render_template("index.html", user_email=session_id)
  
   
    else:
        return render_template("login.html")


@app.get('/check_session')
def check_session():
    if "user" in session:
        print("True")
        return jsonify({'session_valid': True})
    else:
        print("False")
        return jsonify({'session_valid': False})
    


@app.get('/resume_upload2')
def resume_upload2():
    if "user" in session:
        session_id = session["user"]
        questions[session['user']] = {"education_status":[[]], "cand-details":[], "previous_chat":[], "pdf_content":[]}
        return render_template("index.html", user_email=session_id)
 
    else:
        return render_template("login.html")


@app.get("/resume_info")
def resume_info():
    resume_info_retrieved = dict(db.child("Resume_Info").get().val())
    lx = []
    lx2 = []
    copy = []
    
    for i in resume_info_retrieved:
        for j in resume_info_retrieved[i]:
            lx.append([resume_info_retrieved[i][j]["name"], resume_info_retrieved[i][j]["email"], resume_info_retrieved[i][j]["phone"], resume_info_retrieved[i][j]["linkedin"], resume_info_retrieved[i][j]["github"], resume_info_retrieved[i][j]["portfolio"], resume_info_retrieved[i][j]["job_title"], resume_info_retrieved[i][j]["tech_stack"], resume_info_retrieved[i][j]["work_exp_summary"], resume_info_retrieved[i][j]["location"]])                                                                        
    
    for i in lx:
        if i[0] not in copy:
            copy.append(i[0])
            lx2.append(i)

    return render_template("resume_info.html", lx=lx2)


@app.get("/demo")
def demo():
    return render_template("demo.html")

@app.get("/users_list")
def users_list():
    if "user" in session:
        print("I am in session")
        session_id = session["user"]

        user_name = session_id.split("@")[0]

        def feedback_extract(user_id):

            try:
                #Extracting Feedback
                val = dict(db.child("users").child(user_id).child("feedback").get().val())
                feedback = val["feedback"]
                email = val["user_email"]


                #Extracting Dates
                dates_used = dict(db.child("users").child(user_id).child("dates_used").get().val())
                dates_list = list(dates_used.keys())

            
                if len(dates_list) > 1:
                    # Convert the list to a DataFrame
                    df = pd.DataFrame(dates_list, columns=['dates'])

                    # Convert the 'dates' column to datetime format
                    df['dates'] = pd.to_datetime(df['dates'], format='%m-%d-%y')

                    # Sort the DataFrame by the 'dates' column in descending order
                    df_sorted = df.sort_values(by='dates', ascending=False)

                    # Convert the sorted DataFrame back to a list
                    sorted_dates = df_sorted['dates'].dt.strftime('%m-%d-%y').tolist()

                    final_date = sorted_dates[0]

                else:
                    final_date = dates_list[0]

                return [email, feedback, final_date]
            
            except:
                pass


        users_id_list = dict(db.child("users").get().val())

        user_id = list(users_id_list.keys())

        lx = []

        for i in user_id:
            val = feedback_extract(i)

            if val is not None:
                lx.append(val)


        return render_template("table.html", lx = lx, user_name=user_name)

    else:
        return render_template("login.html")

@app.get("/training_page")
def training_page():

    session_id = session["user"]
    user_name = session_id.split("@")[0]
    
    if "admin" in session:
        return render_template("tr2.html", data=False, user_name=user_name)
    
    else:
        return render_template("tr.html", user_name=user_name)


@app.post('/upload_tr')
def upload_tr():
    if 'training_data' not in request.files:
        return 'No file part'
    
    file = request.files['training_data']
    
    if file.filename == '':
        return 'No selected file'
    
    if file:
        file_path = f"{app.config['UPLOAD_FOLDER']}/" + file.filename
        file.save(file_path)
        
        file_extension = os.path.splitext(file_path)[1].lower()

        if file_extension == '.pdf':
            pass


        elif file_extension == '.docx':
            convert_resume =  convert_to_pdf(file_path, app.config['UPLOAD_FOLDER'])
            file_path = file_path[:-5]+".pdf"
            

        elif file_extension == '.doc':
            convert_resume =  convert_to_pdf(file_path, app.config['UPLOAD_FOLDER'])
            file_path = file_path[:-4]+".pdf"


        elif file_extension == '.txt':
            convert_resume =  convert_to_pdf(file_path, app.config['UPLOAD_FOLDER'])
            file_path = file_path[:-4]+".pdf"

        elif file_extension == '.rtf':
            convert_resume =  convert_to_pdf(file_path, app.config['UPLOAD_FOLDER'])
            file_path = file_path[:-4]+".pdf"

        else:
            return "Unsupported file type."
    

        loader = PDFMinerLoader(file_path)
        data = loader.load()

        class Document:
            def __init__(self, metadata, page_content):
                self.metadata = metadata
                self.page_content = page_content

        extracted_text = ""
        for page in data:
            extracted_text += page.page_content

        extracted_text_clean =  extracted_text.replace('\n\n', '\n')

        anthropic_api_key = "" #Add the necessary key here
        
        client = anthropic.Anthropic(
            # defaults to os.environ.get("ANTHROPIC_API_KEY")
            api_key=anthropic_api_key,
        )

        system_message = "chunk the content for fine tuning LLM and be retrievable via RAG via multiple types of prompts.  Do not summarize the information in the chunk. Ensure no loss of information in the chunks created.  For each chunk, identify and create as many as relevant hashtags based on the content of chunk to help improve the retrieval of the content. Include hyperlinks as HTML tags for easy retrieval. Ensure response contains chunks and is in JSON format.  "
        #system_message = "summarize the article, extracting all key points related to professional development, career, advisory, career path. Do not include any reference to the article. Identify key hashtags associated with the content in the article and include them in the response as indicated by #.  Ensure all the key points pertinent to career is included in the generated response. do not include any reference about the article. keep the generated summary to be 5000 words or less. Do not include any name of person, company. Do not include any personally identifiable information. Do not include any racial, bias. Ensure the response is in single paragraph."

        message = client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=8190,
            temperature=0,
            system = system_message,
            #system="You are an expert career advisor, who offers empathetic counseling and actionable advice, offer tailored and contextualized advice. Ensure no response is within the context of the ask. All subsequent prompts should be tracked under session_ID irekommend_001. Ensure responses across the multiple session_ID remain different and does not intermingle. \n",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": extracted_text_clean
                            #"text": "Candidate is looking for advice on their career. Based on the resume, create a list of most asked questions which candidate may ask. Ensure questions address candidate's intent for resources to get promoted, career path and decision making, get salary or pay hike, or get a new job or acquire a new skill. Ensure the response is in JSON format and includes the best prompt for Claude to retrieve the response for each question. One of these prompts would be a subsequent prompt to this current prompt, so generate the prompt accordingly. Ensure no question is more than 20 words long. The resume content is - \"Python Developer\nEmail: sapxxxx@gmail.com\nPh #: 908-123-456\nProfessional Summary\n●\tOver 6 years of IT Experience in design, development, testing and implementation of various standalone and client-server architecture-based enterprise application software in Python on different domains.\n●\tExperience of Programming using Object Oriented Programming (OOPs concept) and software development life cycle (SDLC), architecting scalable platforms, object-oriented programming, database design and agile methodologies.\n●\tExperienced of software development in Python (libraries used: libraries- Beautiful Soup, numpy, scipy, matplotlib, python-twitter, Pandas data frame, network, urllib2, MySQL dB for database connectivity).\n●\tExperienced in designing web pages and Graphical user interfaces, front end layouts on the web by using HTML, DHTML, CSS, Bootstrap framework, XML, JavaScript.\n●\tExperience in developing web services (WSDL, SOAP and REST) and consuming web services with Python programming language.\n●\tExperience of software development in Python and IDEs : pycharm , sublime text , Jupyter Notebook.\n●\tExperience in working with Python ORM Libraries including Django ORM, SQLAlchemy.\n●\tExperience in writing Sub Queries, stored procedures, Triggers, Cursors, and Functions on MySQL and PostgreSQL databases.\n●\tGood knowledge of version control software - CVS, SVN, GitHub\n●\tHaving experienced in Agile Methodologies, Scrum stories and sprints experience in a Python based environment, along with data analytics, data wrangling and Excel data extracts.\n●\tGood working knowledge in UNIX and Linux shell environments using command line utilities.\n●\tPossess good interpersonal, analytical presentation Skills, ability to work in Self-managed and Team environments.\n●\tA good team player with good technical, communication & interpersonal skills. \n●\tMotivated and determined to deliver productive high quality, complete deliverables within deadlines with minimal supervision.\n\nTechnical Skills:\nLanguages\tPython, SQL\nOperating systems\tWindows, Linux\nPython Libraries\tPanda, Pycharm, PyUnit, PyQt, Numpy, urllib2, Beautiful Soup, SciPy, Matplotlib\nFrameworks\tDjango, Flask, Web2py, Pyramid, Cubic Web\nWeb Technologies\tHTML5, CSS3, JavaScript, TypeScript, Ajax, XML\nDatabases\tCassandra, MongoDB, MySQL, MSSQL, SQL Server, Oracle\nVersion Control/CI Tools\tGit, GitHub, Jenkins\nIDEs Tools\tSublime Text, Spyder, PyCharm, Eclipse, Django, Python IDLE\nWeb/Application Servers\tApache Tomcat, WebSphere, WebLogic\nBug Tracking Tools\tJira, BugZilla\n\nProfessional Experience:\nLarge Bank in USA \t\t\t\t\t\t\t\tFeb 2020 – Till Date\nRole: Python Developer\nResponsibilities:\n●\tParticipated in various stages of Software development life cycle (SDLC), Software Testing Life Cycle (STLC) and QA methodologies from project definition to post-deployment documentation.\n●\tUsed Python Django framework to design and develop a web application using MVT - Model view template architecture.\n●\tResponsible for developing impressive UI using HTML, jQuery, CSS and Bootstrap.\n●\tClean data and processed third party spending data into maneuverable deliverables within specific format with Excel macros and python libraries such as NumPy, SQLAlchemy and matplotlib.\n●\tInvolved in development of Web Services using REST for sending and getting data from the external interface in the JSON format.\n●\tAnalyzing various logs that are been generating and predicting/forecasting next occurrence of event with various Python libraries.\n●\tDevelop Automation Scripts and programming libraries that interface with various devices and deal with repetitive tasks such as configuration and extraction of CLI outputs using Python.\n●\tInvolved in development of Web Services using SOAP for sending and getting data from the external interface in the XML format.\n●\tDeveloped the required XML Schema documents and implemented the framework for parsing XML documents.\n●\tParticipated in Version controlling process using GitHub, Git.\n●\tPerformed efficient delivery of code based on principles of Test-Driven Development (TDD) and continuous integration to keep in line with Agile Software Methodology principles.\nEnvironment: Python, Django, NumPy, Matplotlib, HTML, jQuery, CSS, Bootstrap, EC2, SOAP, XML, GITHUB, Agile, Windows.\n\nCompany: Large Bank in India\t\t\t\t\t\t\tDec 2016 – Dec 2019\nRole: Python Developer\nResponsibilities:\n●\tResponsible for gathering requirements, system analysis, design, development, testing and deployment.\n●\tDeveloped consumer-based features and applications using Python, Django, HTML, behavior Driven Development (BDD) and pair-based programming.\n●\tDeveloped user interface using CSS, HTML, Bootstrap, JavaScript.\n●\tUsed Pandas API to put the data as time series and tabular format for east timestamp data manipulation and retrieval.\n●\tWriting Python scripts with Cloud Formation templates to automate installation of Auto scaling, EC2, VPC, and other services.\n●\tDeveloped the required XML Schema documents and implemented the framework for parsing XML documents. \n●\tWorked on Element Tree XML API in python to parse XML documents and load the data in database.\n●\tAutomated the existing scripts for performance calculations using NumPy and SQL alchemy.\n●\tIncreased the speed of pre-existing search indexes through Django ORM optimizations.\n●\tCollaborated with internal teams to convert end user feedback into meaningful and improved solutions.\n●\tWorked in the Agile methodology and applied principles of agile to keep project on track.\n●\tManaged project timelines and communicate with scrum master and clients to ensure project progress satisfactorily.\n●\tLed sprint reviews and daily scrum meetings to touch base with whole team and ensure that all members were performing satisfactorily in automation team.\n●\tDeveloped various Python scripts to find vulnerabilities with SQL Queries by doing SQL injection, permission checks and performance analysis.\n●\tDeveloped scripts to migrate data from proprietary database to PostgreSQL.\n●\tLogged user stories and acceptance criteria in JIRA for features by evaluating output requirements and formats.\n●\tCreated Git repository and added to GitHub project.\nEnvironment: Python, Django, HTML, CSS, Bootstrap, NumPy, Pandas, AWS, EC2, VPC, Jira, XML, XML, SQL Alchemy, jinja2, PyChecker, Agile, Windows.\n\""
                        }
                    ]
                }
            ]
        )

        content_for_ingestion_to_RAG = message.content

        class TextBlock:
            def __init__(self, text):
                self.text = text


        try:
            # Extract text from each TextBlock object in the list
            extracted_texts = [block.text for block in content_for_ingestion_to_RAG]

        except:
            print("do nothing")


        content_for_ingestion_to_RAG_final = ""

        for text in extracted_texts:
            content_for_ingestion_to_RAG_final += text
            content_for_ingestion_to_RAG_final += ". "

        content_for_ingestion_to_RAG_final = content_for_ingestion_to_RAG_final.replace("\n\n", "\n") 

        content_for_ingestion_to_RAG_final = content_for_ingestion_to_RAG_final.strip()

        if content_for_ingestion_to_RAG_final[-1] != "}":
            content_for_ingestion_to_RAG_final = content_for_ingestion_to_RAG_final[:-1]

        #content_for_ingestion_to_RAG_final = content_for_ingestion_to_RAG_final + "}"
        # content_for_ingestion_to_RAG_final = content_for_ingestion_to_RAG_final[:-1]


        data = json.loads(content_for_ingestion_to_RAG_final)

        # Extract chunks and convert to list with appropriate columns
        chunks = data['chunks']

        # Create a list with 'content' and 'hashtags' columns
        output_list = []

        for chunk in chunks:
            # Join the list of hashtags with a single comma, ensuring proper separation
            output_list.append([chunk['content'], ''.join(chunk['hashtags'])])

        # Convert list to DataFrame for better visualization
        chunk_dataframe = pd.DataFrame(output_list, columns=['Content', 'Hashtags'])

        chunk_dataframe['combined'] = chunk_dataframe['Content'] + " "+ chunk_dataframe['Hashtags'] + " Career Advisor" + " cloud Certification " + " certfications"

        def process_hashtags(hashtags):
            # Remove leading and trailing '#' if present, then split by '#'
            split_hashtags = hashtags.strip('#').split('#')

            # Deduplicate the list of hashtags
            unique_hashtags = list(set(split_hashtags))

            # Return the unique hashtags as a comma-separated string
            return ' #'.join(unique_hashtags)


        chunk_dataframe['Processed_Hashtags'] = chunk_dataframe['Hashtags'].apply(process_hashtags)

        # Step 4: Display the updated DataFrame with the new column
        print(chunk_dataframe[['Hashtags', 'Processed_Hashtags']])

        #Mongo DB Connection
        ATLAS_CONNECTION_STRING = os.getenv('mongo_connection_string', 'na')

        # Connect to your Atlas cluster
        client = MongoClient(ATLAS_CONNECTION_STRING)

        # Define collection and index name
        db_name = "Career-Coaching"
        collection_name = "career-advisory"
        atlas_collection = client[db_name][collection_name]
        vector_search_index = "advise"


        def ingest_text_string(text_string, subDomain, vector_search_index, atlas_collection):
            # Step 1: Embed the string using OpenAI embeddings
            embedding_model = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)
            text_embedding = embedding_model.embed_query(text_string)

            text_embedding_str = ".".join(map(str, text_embedding))

            print("text_string" + text_string)
            #print("text_embedding", text_embedding_str)
            # Step 2: Prepare the document (text + embedding) to insert into MongoDB
            doc = {
                "domain": "Career Advisor",
                "subDomain": subDomain,
                "value": text_string,
                "embedding": text_embedding
            }

            # Step 3: Insert the document into the vector search index in MongoDB Atlas
            atlas_collection.insert_one(doc)

            # Return confirmation
            return "Text string successfully ingested into MongoDB Atlas Vector Search."

        # Example usage: Ingest a text string into the vector search
        vector_search = MongoDBAtlasVectorSearch.from_documents(
            documents=[],
            embedding=OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY),
            collection=atlas_collection,
            index_name='advise'
        )


        for _, row in chunk_dataframe.iterrows():
            # Extract values from each row
            text_value = row['combined']
            hashtags = row['Processed_Hashtags']

            # Call the ingest_text_string function with the extracted values
            ingest_text_string(text_value, hashtags, vector_search_index, atlas_collection)

            return render_template("tr2.html", data=True)

    else:
        return "Upload supported file types only (DOC, DOCX, RTF, TXT)"



        # Split PDF into documents
    #     text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=0, separators=["\n\n", "\n", "(?<=\. )", " "], length_function=len)
    #     docs = text_splitter.split_documents(data)

    #     vector_search = MongoDBAtlasVectorSearch.from_documents(
    #     documents = docs,
    #     embedding = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY),
    #     collection = atlas_collection,
    #     index_name = vector_search_index
    #     )

    #     return render_template("tr2.html", data=True)

    # else:
    #     return "Upload supported file types only (DOC, DOCX, RTF, TXT)"
    



@app.post('/upload')
def upload():
    session_id = session["user"]
    initial_message = request.form.get("vendor_name")
    pdf_data[session_id] = initial_message
    initial_message = "Jarvis: H! I'm here to help Career Counsellors, you can ask any questions related to career counselling"
    return render_template('home.html', initial_message=initial_message, session_id=session_id)
    

@app.get("/index")
def index():
    if "user" in session:
        session_id = session["user"]
        user_name = session_id.split("@")[0]
        return render_template("home.html", user_name=user_name)
    
    else:
        return render_template("login.html")


@app.get("/admin_training_page")
def admin_training_page():
    session_id = session["user"]
    user_name = session_id.split("@")[0]
    return render_template("tr.html", user_name=user_name)


@app.post("/admin_training_page_response")
def admin_training_page_response():

    email = request.form["email"]
    password = request.form["password"]

    sa_list = db.child("super_admin").get().val()

    if email in sa_list:

        auth = firebase.auth()

        try:
            user = auth.sign_in_with_email_and_password(email, password)
            session["admin"] = email

        except:
            return "Invalid Username or Password"
        
    else:
        return "Sorry, looks like this email address doesn't have super admin access"
        
    return render_template("tr2.html")
         


@app.get('/reload_user')
def reload_user():
    return redirect("/")
    
@app.get("/login")
def login():
    return render_template("login.html")

@app.post("/login_response")
def login_response():

    email = request.form["email"]
    password = request.form["password"]

    # Get a reference to the auth service
    auth = firebase.auth()

    # Log the user in
    try:
        user = auth.sign_in_with_email_and_password(email, password)
        session["user"] = email
        return redirect("/")
    
    except Exception as e:
        
        return render_template("login.html", show_alert=True)

    

def check_word_in_string(word, string):

            word_processed = word.replace(" ", "").lower()
            string_processed = string.replace(" ", "").lower()

            return word_processed in string_processed


@app.post('/ask')
def ask_question():

    session_id = request.form['session_id']

    user_response = request.form['user_response']

    resume_text = pdf_data[session_id]


    if session_id not in questions:
        questions[session_id] = {"education_status":[[]], "cand-details":[], "previous_chat":[]}

    questions[session_id]["cand-details"].append(user_response)
    
    c = len(questions[session_id]["cand-details"])
    
    c = c-1
    
    if c == 0:

        client = anthropic.Anthropic(

            api_key=api_key,
        )

        # Define the prompt template for career counselling focusing only on resume
        career_prompt = PromptTemplate(
            template="""

                Hi, I’m Swift! I specialize in comprehensive vendor and product analysis, equipped with insights and expertise.
                Let's begin with a detailed evaluation of the vendor:

                You are expected to perform Comprehensive Vendor and Product Analysis. As the first step, perform Vendor Overview 
                and Market Position - Provide an overview of the vendor, including its history, mission, and core business focus. 
                Be as detailed as possible. The vendor is: {resume_text}
                
                """,
            input_variables=["resume_text"]
        )

        # Create the LLM chain with only the resume as input
        career_chain = LLMChain(llm=llm2, prompt=career_prompt)

        # Generate bot response using only the resume_text
        bot_response = career_chain.run(resume_text=resume_text)


        career_prompt = PromptTemplate(
            template="""

                Based on the following analysis:

                Vendor Overview: {overview}

                Generate three example questions related to market positioning, milestones, and competitive analysis.
                Include criteria such as value chain alignment, technical features, AI capabilities, and customer support. Ensure questions are concise 
                and practical.

                Make sure response is in json format.

                Json Key Names should be follow_up_questions, industry_specific_questions and role_specific_questions.

                Questions should be returned inside list. Something like this [Q1, Q2]

                Questions:

                """,
            input_variables=["overview"]
        )

        # Create the LLM chain with only the resume as input
        career_chain = LLMChain(llm=llm2, prompt=career_prompt)

        # Generate bot response using only the resume_text
        bot_response2 = career_chain.run(overview=bot_response)

        
        bot_response2 = ast.literal_eval(bot_response2)

        bt2 = []
        for i in bot_response2:
            bt2.extend(bot_response2[i])
        
        bot_response = bot_response+"\n\n"


            
    elif c >= 1:

        def date_exist(user_id):

            #Creating date if noy exists
            try:
                val = dict(db.child("users").child(user_id).child("dates_used").get().val())

                #Extract Todays Date
                today_date = datetime.now().strftime("%m-%d-%y")
                val = val[today_date]

            except:
                try:
                    val = dict(db.child("users").child(user_id).child("dates_used").get().val())

                except:
                    val = {}

                #create date for particular user
                today_date = datetime.now().strftime("%m-%d-%y")

                val[today_date] = 10

                db.child("users").child(user_id).child("dates_used").set(val)


        def request_left(user_id):
            val = dict(db.child("users").child(user_id).child("dates_used").get().val())
            today_date = datetime.now().strftime("%m-%d-%y")
            return val[today_date]

        def decrement_request(user_id):
            val = dict(db.child("users").child(user_id).child("dates_used").get().val())
            today_date = datetime.now().strftime("%m-%d-%y")
            balance = val[today_date]-1
            val[today_date] = balance
            db.child("users").child(user_id).child("dates_used").set(val)

        def feedback_check(user_id):
            try:
                val = dict(db.child("users").child(user_id).child("feedback").get().val())

                #Extract feedback status
                val = val["feedback_status"]
                return val

            except:
                #create date for particular user
                val = {"feedback_status": False}
                db.child("users").child(user_id).child("feedback").set(val)
                return False


        username = session["user"]
        hashed_username = generate_email_integer_hash(username)


        date_exist(hashed_username)

        remaining_request = request_left(hashed_username)

        if remaining_request > 0:

            documents = vector_search(questions[session_id]["cand-details"][c])
     
            data = format_docs(documents)

            pc = questions[session_id]["previous_chat"]

            career_prompt = PromptTemplate(
                template="""
                You are an expert market research agent with ability to browse web content to pull relevant content around various vendor products. You have understanding of technology vendor products. 
                Be as detailed as possible. Include the URL of the reference website.
                The vendor is {resume_text}

                Question: {question}
                Answer:
                """,
                input_variables=["question", "resume_text"]
            )


            career_chain = LLMChain(llm=llm2, prompt=career_prompt)

            bot_response = career_chain.run(resume_text=resume_text, question=questions[session_id]["cand-details"][c])

            career_prompt = PromptTemplate(
            template="""

                    Based on the following analysis:

                    Vendor Overview: {overview}

                    Generate three example questions related to market positioning, milestones, and competitive analysis, 
                    followed by creating a Pugh Matrix evaluating the vendor against its competitors. Include criteria such as 
                    value chain alignment, technical features, AI capabilities, and customer support. Ensure questions are concise 
                    and practical.

                    Make sure response is in json format.

                    Json Key Names should be follow_up_questions, industry_specific_questions and role_specific_questions.

                    Questions should be returned inside list. Something like this [Q1, Q2]

                    Questions:
            
                """,
                input_variables=["overview"]
            )

            # Create the LLM chain with only the resume as input
            career_chain = LLMChain(llm=llm2, prompt=career_prompt)

            # Generate bot response using only the resume_text
            bot_response2 = career_chain.run(overview=bot_response)
            
            bot_response2 = ast.literal_eval(bot_response2)

            bt2 = []
            for i in bot_response2:
                bt2.extend(bot_response2[i])

            print()
            print("Q)", questions[session_id]["cand-details"][c])
            print("Answer)", bot_response)

            prev_chat = questions[session_id]["cand-details"][c]

            questions[session_id]["previous_chat"].append({"user_question": prev_chat, "bot_response": bot_response})

            decrement_request(hashed_username)


        else:
            bot_response = "You have reached your daily limit of 15 questions. Please try again tomorrow!"
            questions[session_id] = []


    feedback_required = False

    print("Count", c)

    if c == 4:
        if feedback_check(hashed_username):
            print(feedback_check(hashed_username))
            feedback_required = False

        else:
            print(feedback_check(hashed_username))
            feedback_required = True
   
    return jsonify({'bot_response': bot_response, 'feedback_required': feedback_required, "questions": bt2})


@app.post("/tutorial")
def tutorial():
    val = request.get_json()
    username = val["email"]
    hashed_username = generate_email_integer_hash(username)
    print("session User id", generate_email_integer_hash(session["user"]))
    print(hashed_username)
    print("In Tutorial")
    print(val)

    try:
        val = dict(db.child("user_details").child(hashed_username).get().val())
        
        if val["count"]>=1:
            val['count'] = val['count']-1
            db.child("user_details").child(hashed_username).set(val)
            return jsonify({'status': True})
        
        else:
            return jsonify({'status': False})
        
    except:
        db.child("user_details").child(hashed_username).set({"count":0})
        return jsonify({'status': True})



@app.post('/feedback')
def feedback():
    data = request.get_json()
    session_id = data.get('session_id')
    rating = data.get('rating')
    feedback = data.get('feedback')

    user_id = generate_email_integer_hash(session["user"])

    val = dict(db.child("users").child(user_id).child("feedback").get().val())

    #Add Feedback
    val["feedback_status"] = True
    val["rating"] = rating
    val["feedback"] = feedback
    val["user_email"] = session_id

    print(val)

    db.child("users").child(user_id).child("feedback").set(val)

    print(f"Feedback received: Session ID: {session_id}, Rating: {rating}, Feedback: {feedback}")
    return jsonify({'status': 'success'})

@app.get("/sign_up")
def sign_up():
    return render_template("sign_up.html")

@app.post("/sign_up_response")
def sign_up_response():

    user_name = request.form["username"]
    email = request.form["email"]
    password_1 = request.form["password"]

    try:    
        auth.create_user_with_email_and_password(email, password_1)
        username = email
        hashed_username = generate_email_integer_hash(username)
        db.child("user_details").child(hashed_username).set({"user_name":user_name, "count":1})

    except:
        return "Account already exists"
    

    return render_template("login.html")



# Function to generate the PDF with a clickable link and structured content
def generate_pdf(file_name, sections):
    pdf = SimpleDocTemplate(file_name, pagesize=A4)
    styles = getSampleStyleSheet()

    # Custom styles
    header_style = ParagraphStyle('HeaderStyle', fontSize=24, leading=30, alignment=1, spaceAfter=20)
    subheader_style = ParagraphStyle('SubHeaderStyle', fontSize=18, leading=24, alignment=1, spaceAfter=15, fontName='Helvetica-Bold')
    body_text_style = ParagraphStyle('BodyTextStyle', fontSize=12, leading=14, alignment=0, spaceAfter=12)

    # Elements to be added to the PDF
    elements = []

    # Add the main header
    header_text = "iMarket Vendor Advisor"
    elements.append(Paragraph(header_text, header_style))

    # Add the "About iRekommend" section
    subheader_text = "About iMarket"
    elements.append(Paragraph(subheader_text, subheader_style))

    about_text = """
    iMarket empowers businesses with expert-level insights for vendor evaluation, competitive analysis, and strategic decision-making. With a proven track record of enhancing market positioning and driving informed choices, our platform leverages real-world data and cutting-edge AI to deliver precise, actionable results.
    """
    elements.append(Paragraph(about_text, body_text_style))
    elements.append(Spacer(1, 0.5 * inch))
    # Add the chat history content
    for section_title, section_content in sections:
        elements.append(Paragraph(section_title, styles['Heading2']))
        
        formatted_content = section_content.replace("\n", "<br/>")
        elements.append(Paragraph(formatted_content, styles['BodyText']))
        elements.append(Spacer(1, 0.5 * inch))
        elements.append(PageBreak())

    # Build the PDF document
    pdf.build(elements)


# New route for exporting the chat history as a PDF
@app.route("/export_chat", methods=["GET"])
def export_chat():
    if "user" in session:
        try:
            session_id = session["user"]
            session_username = session_id.split("@")[0]

            # Retrieve the chat history
            chat = questions.get(session_id, {}).get("previous_chat", [])
            sections = []
            for i in chat:
                quest = i["user_question"].capitalize()
                ans = i["bot_response"]
                q = f"USER: {quest}?"
                a = f"<b>Bot Response:</b> {ans}"
                sections.append((q, a))

            # Define the PDF file path
            pdf_file_path = f"{session_username}_chat_history.pdf"
            
            # Generate the PDF
            generate_pdf(pdf_file_path, sections)

            # Send the PDF file to the user
            return send_file(pdf_file_path, as_attachment=True)

        except Exception as e:
            print(f"Error generating PDF: {e}")
            return "An error occurred while generating the PDF", 500

        finally:
            # Remove the file after sending it to the user
            if os.path.exists(pdf_file_path):
                os.remove(pdf_file_path)
    else:
        return render_template("login.html")


@app.get("/logout")
def logout():
    session_id = session["user"]
    del pdf_data[session_id]
    session.pop("user", None)
    session.pop("admin", None)
    return render_template("login.html")

@app.get("/forget_pass")
def forget_pass():
    return render_template("forget_pass.html", show_content=False)

@app.post('/forget_pass_response')
def forget_pass_response():
    email = request.form["email"]
    auth.send_password_reset_email(email)
    return render_template("forget_pass.html", show_content=True)

if __name__ == '__main__':
    app.run(debug=True, port=815, host="0.0.0.0")



