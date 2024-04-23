import asyncio
import json
import time

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from common_code.config import get_settings
from common_code.http_client import HttpClient
from common_code.logger.logger import get_logger, Logger
from common_code.service.controller import router as service_router
from common_code.service.service import ServiceService
from common_code.storage.service import StorageService
from common_code.tasks.controller import router as tasks_router
from common_code.tasks.service import TasksService
from common_code.tasks.models import TaskData
from common_code.service.models import Service
from common_code.service.enums import ServiceStatus
from common_code.common.enums import FieldDescriptionType, ExecutionUnitTagName, ExecutionUnitTagAcronym
from common_code.common.models import FieldDescription, ExecutionUnitTag
from contextlib import asynccontextmanager

# Imports required by the service's model
# TODO: 1. ADD REQUIRED IMPORTS (ALSO IN THE REQUIREMENTS.TXT)
import requests

settings = get_settings()


class MyService(Service):
    # TODO: 2. CHANGE THIS DESCRIPTION
    """
    This service uses Hugging Face's model hub API to directly query text-to-image AI models
    """

    # Any additional fields must be excluded for Pydantic to work
    _model: object
    _logger: Logger

    def __init__(self):
        super().__init__(
            # TODO: 3. CHANGE THE SERVICE NAME AND SLUG
            name="Hugging Face text-to-image",
            slug="hugging-face-text-to-image",
            url="http://localhost:9090",
            summary=api_summary,
            description=api_description,
            status=ServiceStatus.AVAILABLE,
            # TODO: 4. CHANGE THE INPUT AND OUTPUT FIELDS, THE TAGS AND THE HAS_AI VARIABLE
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
            ],
            has_ai=True,
            # OPTIONAL: CHANGE THE DOCS URL TO YOUR SERVICE'S DOCS
            docs_url="https://docs.swiss-ai-center.ch/reference/core-concepts/service/",
        )
        self._logger = get_logger(settings)

    # TODO: 5. CHANGE THE PROCESS METHOD (CORE OF THE SERVICE)
    def process(self, data):
        # NOTE that the data is a dictionary with the keys being the field names set in the data_in_fields
        # The objects in the data variable are always bytes. It is necessary to convert them to the desired type
        # before using them.
        # raw = data["image"].data
        # input_type = data["image"].type
        # ... do something with the raw data

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


service_service: ServiceService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Manual instances because startup events doesn't support Dependency Injection
    # https://github.com/tiangolo/fastapi/issues/2057
    # https://github.com/tiangolo/fastapi/issues/425

    # Global variable
    global service_service

    # Startup
    logger = get_logger(settings)
    http_client = HttpClient()
    storage_service = StorageService(logger)
    my_service = MyService()
    tasks_service = TasksService(logger, settings, http_client, storage_service)
    service_service = ServiceService(logger, settings, http_client, tasks_service)

    tasks_service.set_service(my_service)

    # Start the tasks service
    tasks_service.start()

    async def announce():
        retries = settings.engine_announce_retries
        for engine_url in settings.engine_urls:
            announced = False
            while not announced and retries > 0:
                announced = await service_service.announce_service(my_service, engine_url)
                retries -= 1
                if not announced:
                    time.sleep(settings.engine_announce_retry_delay)
                    if retries == 0:
                        logger.warning(
                            f"Aborting service announcement after "
                            f"{settings.engine_announce_retries} retries"
                        )

    # Announce the service to its engine
    asyncio.ensure_future(announce())

    yield

    # Shutdown
    for engine_url in settings.engine_urls:
        await service_service.graceful_shutdown(my_service, engine_url)


# TODO: 6. CHANGE THE API DESCRIPTION AND SUMMARY
api_description = """The service is used to query text-to-image AI models from the Hugging Face inference API.\n

 You can choose from any model available on the inference API from the [Hugging Face Hub](https://huggingface.co/models)
 that takes a text(json) as input and outputs an image.
 
It must take only one input text with the following structure:

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

# Define the FastAPI application with information
# TODO: 7. CHANGE THE API TITLE, VERSION, CONTACT AND LICENSE
app = FastAPI(
    lifespan=lifespan,
    title="Hugging Face text-to-image service",
    description=api_description,
    version="0.0.1",
    contact={
        "name": "Swiss AI Center",
        "url": "https://swiss-ai-center.ch/",
        "email": "info@swiss-ai-center.ch",
    },
    swagger_ui_parameters={
        "tagsSorter": "alpha",
        "operationsSorter": "method",
    },
    license_info={
        "name": "GNU Affero General Public License v3.0 (GNU AGPLv3)",
        "url": "https://choosealicense.com/licenses/agpl-3.0/",
    },
)

# Include routers from other files
app.include_router(service_router, tags=["Service"])
app.include_router(tasks_router, tags=["Tasks"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Redirect to docs
@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/docs", status_code=301)
