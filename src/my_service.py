from common_code.config import get_settings
from common_code.logger.logger import get_logger, Logger
from common_code.service.models import Service
from common_code.service.enums import ServiceStatus
from common_code.common.enums import FieldDescriptionType, ExecutionUnitTagName, ExecutionUnitTagAcronym
from common_code.common.models import FieldDescription, ExecutionUnitTag
from common_code.tasks.models import TaskData
# Imports required by the service's model
import requests
import json

api_description = """The service is used to query text-to-image AI models from the Hugging Face inference API.\n

 You can choose from any model available on the inference API from the [Hugging Face Hub](https://huggingface.co/models)
 that takes a text(json) as input and outputs an image.

The model must take only one input text with the following structure:

```
{
    "inputs" : "your input text"
}
```

 This service takes two input files:
  - A json file that defines the model you want to use and your access token.
  - A text file.

 json_description.json example:
  ```
 {
    "api_token": "your_token",
    "api_url": "https://api-inference.huggingface.co/models/stabilityai/stable-cascade"
 }
 ```
 This is used for image generation based on a description.

 input_text example:

 ```
 A majestic Hummingbird
 ```

 The model may need some time to load on Hugging face's side, you may encounter an error on your first try.

 Helpful trick: The answer from the inference API is cached, so if you encounter a loading error try to change the
 input to check if the model is loaded.
 """

api_summary = """This service is used to query text-to-image models from Hugging Face
"""
api_title = "Hugging Face text-to-image service"
version = "1.0.0"

settings = get_settings()


class MyService(Service):
    """
    This service uses Hugging Face's model hub API (inference API) to directly query text-to-image AI models
    """

    # Any additional fields must be excluded for Pydantic to work
    _model: object
    _logger: Logger

    def __init__(self):
        super().__init__(
            name="Hugging Face text-to-image",
            slug="hugging-face-text-to-image",
            url=settings.service_url,
            summary=api_summary,
            description=api_description,
            status=ServiceStatus.AVAILABLE,
            data_in_fields=[
                FieldDescription(
                    name="json_description",
                    type=[
                        FieldDescriptionType.APPLICATION_JSON
                    ],
                ),
                FieldDescription(
                    name="input_text",
                    type=[
                        FieldDescriptionType.TEXT_PLAIN
                    ]
                ),
            ],
            data_out_fields=[
                FieldDescription(
                    name="result", type=[FieldDescriptionType.IMAGE_PNG,
                                         FieldDescriptionType.IMAGE_JPEG]
                ),
            ],
            tags=[
                ExecutionUnitTag(
                    name=ExecutionUnitTagName.NATURAL_LANGUAGE_PROCESSING,
                    acronym=ExecutionUnitTagAcronym.NATURAL_LANGUAGE_PROCESSING,
                ),
                ExecutionUnitTag(
                    name=ExecutionUnitTagName.IMAGE_GENERATION,
                    acronym=ExecutionUnitTagAcronym.IMAGE_GENERATION,
                ),
            ],
            has_ai=True,
            docs_url="https://docs.swiss-ai-center.ch/reference/services/hugging-face-text-to-image/",
        )
        self._logger = get_logger(settings)

    def process(self, data):

        try:
            json_description = json.loads(data['json_description'].data.decode('utf-8'))
            api_token = json_description['api_token']
            api_url = json_description['api_url']
        except ValueError as err:
            raise Exception(f"json_description is invalid: {str(err)}")
        except KeyError as err:
            raise Exception(f"api_url or api_token missing from json_description: {str(err)}")

        headers = {"Authorization": f"Bearer {api_token}"}

        def is_valid_json(json_string):
            try:
                json.loads(json_string)
                return True
            except ValueError:
                return False

        def text_to_image_query(payload):
            response = requests.post(api_url, headers=headers, json=payload)
            return response.content

        input_text_bytes = data['input_text'].data
        json_input_text = f'{{ "inputs" : "{input_text_bytes.decode("utf-8")}" }}'
        json_payload = json.loads(json_input_text)
        image_bytes = text_to_image_query(json_payload)

        if is_valid_json(image_bytes):
            data = json.loads(image_bytes)
            if 'error' in data:
                raise Exception(data['error'])

        return {
            "result": TaskData(data=image_bytes,
                               type=FieldDescriptionType.IMAGE_PNG)
        }
