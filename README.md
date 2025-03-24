[![PyPI](https://img.shields.io/pypi/v/aryn-sdk)](https://pypi.org/project/aryn-sdk/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/aryn-sdk)](https://pypi.org/project/aryn-sdk/)
[![Slack](https://img.shields.io/badge/slack-sycamore-brightgreen.svg?logo=slack)](https://join.slack.com/t/sycamore-ulj8912/shared_invite/zt-23sv0yhgy-MywV5dkVQ~F98Aoejo48Jg)
[![Docs](https://img.shields.io/badge/Docs-8A2BE2)](https://docs.aryn.ai)
![License](https://img.shields.io/github/license/aryn-ai/sycamore)

`aryn-sdk` is a simple client library for interacting with Aryn DocParse.


## Partition (Parse) files

Partition PDF files with Aryn DocParse through `aryn-sdk`:

```python
from aryn_sdk.partition import partition_file

with open("partition-me.pdf", "rb") as f:
    data = partition_file(
        f,
        use_ocr=True,
        extract_table_structure=True,
        extract_images=True
    )
elements = data['elements']
```

Convert a partitioned table element to a pandas dataframe for easier use:

```python
from aryn_sdk.partition import partition_file, table_elem_to_dataframe

with open("partition-me.pdf", "rb") as f:
    data = partition_file(
        f,
        use_ocr=True,
        extract_table_structure=True,
        extract_images=True
    )

# Find the first table and convert it to a dataframe
df = None
for element in data['elements']:
    if element['type'] == 'table':
        df = table_elem_to_dataframe(element)
        break
```

Or convert all partitioned tables to pandas dataframes in one shot:

```python
from aryn_sdk.partition import partition_file, tables_to_pandas

with open("partition-me.pdf", "rb") as f:
    data = partition_file(
        f,
        use_ocr=True,
        extract_table_structure=True,
        extract_images=True
    )
elements_and_tables = tables_to_pandas(data)
dataframes = [table for (element, table) in elements_and_tables if table is not None]
```

Visualize partitioned documents by drawing on the bounding boxes:

```python
from aryn_sdk.partition import partition_file, draw_with_boxes

with open("partition-me.pdf", "rb") as f:
    data = partition_file(
        f,
        use_ocr=True,
        extract_table_structure=True,
        extract_images=True
    )
page_pics = draw_with_boxes("partition-me.pdf", data, draw_table_cells=True)

from IPython.display import display
display(page_pics[0])
```

> Note: visualizing documents requires `poppler`, a pdf processing library, to be installed. Instructions for installing poppler can be found [here](https://pypi.org/project/pdf2image/)

Convert image elements to more useful types, like PIL, or image format typed byte strings

```python
from aryn_sdk.partition import partition_file, convert_image_element

with open("my-favorite-pdf.pdf", "rb") as f:
    data = partition_file(
        f,
        extract_images=True
    )
image_elts = [e for e in data['elements'] if e['type'] == 'Image']

pil_img = convert_image_element(image_elts[0])
jpg_bytes = convert_image_element(image_elts[1], format='JPEG')
png_str = convert_image_element(image_elts[2], format="PNG", b64encode=True)
```


## Document storage

The DocParse storage APIs provide a simple interface to interact with documents processed and stored by DocParse.


### DocSets
The DocSet APIs allow you create, list, and delete DocSets to store your documents in.

```python
from aryn.client.client import Client

client = Client()

# Create a new DocSet and get the ID.
new_docset = client.create_docset(name="My DocSet")
docset_id = new_docset.value.docset_id

# Retrieve a specific DocSet by ID.
docset = client.get_docset(docset_id=docset_id).value

# List all of the DocSets in your account.
docsets = client.list_docsets().get_all()

# Delete the DocSet you created
client.delete_docset(docset_id=docset_id)
```

### Documents

The document APIs let you interact with individual documents, including the
ability to retrieve the original file.

```python
from aryn.client.client import Client

client = Client()

# Iterate through the documents in a single DocSet
docset_id = None # my docset id
paginator = client.list_docs(docset_id = docset_id)
for doc in paginator:
    print(f"Doc {doc.name} has id {doc.doc_id}")

# Get a single document
doc_id = None # my doc id
doc = client.get_doc(docset_id=docset_id, doc_id=doc_id).value

# Get the original pdf of a document and write to a file.
with open("/path/to/outfile", "wb") as out:
    client.get_doc_binary(docset_id=docset_id, doc_id=doc_id, file=out)

# Delete a document by id.
client.delete_doc(docset_id=docset_id, doc_id=doc_id)
client.get_doc_binary()
```

## Query

You can run vector and keyword search queries on the documents stored in DocParse storage.

```python
from aryn_sdk.client.client import Client

client = Client()
docset_id = None # my docset id

# Search by query
search_request = SearchRequest(query="test_query")
results = client.search(docset_id=docset_id, query="my query")

# Search by filter
filter_request = SearchRequest(query="test_filter_query", properties_filter="(properties.entity.name='test')")
results = client.search(docset_id=docset_id, query="my query")
```

## Extract additional properties (metadata) from your documents

You can use LLMs to extract additional metadata from your documents in DocParse storage. These are stored as properties, and are extracted from every document in your DocSet.

```python
from aryn_sdk.client.client import Client
from aryn_sdk.types.schema import Schema, SchemaField

client = Client()
docset_id = None # my docset id
schema_field = SchemaField(name="name", field_type="string")
schema = Schema(fields=[schema_field])

# Extract properties

client_obj.extract_properties(docset_id=docset_id, schema=schema)

# Delete extracted properties
client_obj.delete_properties(docset_id=docset_id, schema=schema)
```

### Async APIs

#### Partitioning - Single Task Example
```python
import time
from aryn_sdk.partition import partition_file_async_submit, partition_file_async_result

with open("my-favorite-pdf.pdf", "rb") as f:
    response = partition_file_async_submit(
        f,
        use_ocr=True,
        extract_table_structure=True,
    )

task_id = response["task_id"]

# Poll for the results
while True:
    result = partition_file_async_result(task_id)
    if result["task_status"] != "pending":
        break
    time.sleep(5)
```

Optionally, you can also set a webhook for Aryn to call when your task is completed:

```python
partition_file_async_submit("path/to/my/file.docx", webhook_url="https://example.com/alert")
```

Aryn will POST a request containing a body like the below:
```json
{"done": [{"task_id": "aryn:t-47gpd3604e5tz79z1jro5fc"}]}
```

#### Multi-Task Example

```python
import logging
import time
from aryn_sdk.partition import partition_file_async_submit, partition_file_async_result

files = [open("file1.pdf", "rb"), open("file2.docx", "rb")]
task_ids = [None] * len(files)
for i, f in enumerate(files):
    try:
        task_ids[i] = partition_file_async_submit(f)["task_id"]
    except Exception as e:
        logging.warning(f"Failed to submit {f}: {e}")

results = [None] * len(files)
for i, task_id in enumerate(task_ids):
    while True:
        result = partition_file_async_result(task_id)
        if result["task_status"] != "pending":
            break
        time.sleep(5)
    results[i] = result
```

#### Cancelling an async task

```python
from aryn_sdk.partition import partition_file_async_submit, partition_file_async_cancel
        task_id = partition_file_async_submit(
                    "path/to/file.pdf",
                    use_ocr=True,
                    extract_table_structure=True,
                    extract_images=True,
                )["task_id"]

        partition_file_async_cancel(task_id)
```

#### List pending tasks

```
from aryn_sdk.partition import partition_file_async_list
partition_file_async_list()
```

#### Async Properties (Extract and Delete) example

```python
from aryn_sdk.client.client import Client
from aryn_sdk.types.schema import Schema, SchemaField

client = Client()

# Run extract_properties and delete_properties asynchronously
schema_field = SchemaField(name="name", field_type="string")
schema = Schema(fields=[schema_field])
client_obj.extract_properties_async(docset_id=docset_id, schema=schema) # async implementation
client_obj.delete_properties_async(docset_id=docset_id, schema=schema) # async implementation

# Check the status and get the task result
task = None # my task id
get_async_result = client.get_async_result(task=task_id)

# List all outstanding async tasks.
client.list_async_tasks()
```
