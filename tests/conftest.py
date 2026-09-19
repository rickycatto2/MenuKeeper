import os
import tempfile
# All automated tests use their own database and never touch household data.
_test_data=tempfile.TemporaryDirectory(prefix='menukeeper-test-')
os.environ['DATA_DIR']=_test_data.name
os.environ['OPENAI_API_KEY']=''
