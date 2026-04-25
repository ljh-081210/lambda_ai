FROM public.ecr.aws/lambda/python:3.11

RUN pip3 install --no-cache-dir pillow boto3

COPY app.py ${LAMBDA_TASK_ROOT}

CMD [ "app.lambda_handler" ]
