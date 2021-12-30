#!/usr/bin/env python3

def set_response_without_ldjson(datastore_path):
    test_return_data = """<html>
       <body>
     Some initial text<br>
     <p>Which is across multiple lines</p>
     <br>
     So let's see what happens.  <br>
     <div class="sametext">Some text thats the same</div>
     <div class="changetext">Some text that will change</div>     
     </body>
     </html>
"""

    with open(os.path.join(datastore_path, "endpoint-content.txt"), "w") as f:
        f.write(test_return_data)
    return None

