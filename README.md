# Hugging face text to image service

This service uses hugging face's inference API to query text-to-image AI models.
Any model from the [hub](https://huggingface.co/models) available on the 
[inference API](https://huggingface.co/docs/api-inference/en/index) that outputs an image and takes a json input with the 
following structure can be used:

```
{
    "inputs" : "your input text"
}
```


_Check the [related documentation](https://docs.swiss-ai-center.ch/reference/services/hugging-face-text-to-image) for more information._