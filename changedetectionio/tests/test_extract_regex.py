#!/usr/bin/env python3

def set_multiline_response(datastore_path):
    test_return_data = """<html>
       <body>
     
     <p>Something <br>
        across 6 billion multiple<br>
        lines
     </p>
     
     <div>aaand something lines</div>
     <br>
     <div>and this should be</div>
     </body>
     </html>
    """

    with open(os.path.join(datastore_path, "endpoint-content.txt"), "w") as f:
        f.write(test_return_data)

    return None


