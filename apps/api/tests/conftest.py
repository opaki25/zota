import os

# Set test configuration before any test module imports the application.
os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['TESTING'] = 'true'
os.environ['SECURE_COOKIES'] = 'false'
os.environ['VERCEL_ENV'] = ''
