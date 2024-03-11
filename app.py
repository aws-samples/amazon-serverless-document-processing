from aws_cdk import (
    Duration,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_lambda_event_sources as eventsources,
    aws_apigateway as apigateway,
    aws_rekognition as rekognition,
    aws_s3 as s3,
    Stack,
    App,    
    CfnOutput,
    RemovalPolicy,   
    aws_sns as sns,
    aws_sns_subscriptions as snssubs,
    aws_sqs as sqs
)
from constructs import Construct

class CdklambdaStack(Stack):

    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        # Input Bucket
        self.input_bucket = s3.Bucket(self, 'input-bucket',
                                      versioned=True,
                                      bucket_name='docs-landing-bucket',
                                      encryption=s3.BucketEncryption.S3_MANAGED,
                                      block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
                                      enforce_ssl=True)
        
        # Valid Bucket
        self.valid_bucket = s3.Bucket(self, 'valid-bucket',
                                      versioned=True,
                                      bucket_name='valid-docs-bucket',
                                      encryption=s3.BucketEncryption.S3_MANAGED,
                                      block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
                                      enforce_ssl=True)
        
        # InValid Bucket
        self.invalid_bucket = s3.Bucket(self, 'invalid-bucket',
                                      versioned=True,
                                      bucket_name='invalid-docs-bucket',
                                      encryption=s3.BucketEncryption.S3_MANAGED,
                                      block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
                                      enforce_ssl=True)
        
        # Create Rekognition Collection
        rekognition_collection = rekognition.CfnCollection(self, "RekognitionCollection",collection_id="MyRekognitionCollection")

        # Create a resource policy for the collection
        resource_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": "*",
                    "Action": "rekognition:*",
                    "Resource": "*"
                }
            ]
        }        

        python_lambda_kwargs = {
            'handler': 's3event.lambda_handler',
            'runtime': lambda_.Runtime.PYTHON_3_9,
            'timeout': Duration.minutes(10),
            'memory_size': 4096
        }
        # Create the Rest API
        rest_api = apigateway.RestApi(
            self, "RestApi",
            endpoint_types=[apigateway.EndpointType.REGIONAL]
        )

        # Trigger Textract Lambda
        trigger_textract = lambda_.Function(self, 'file-upload-trigger', **python_lambda_kwargs,
                                            code=lambda_.Code.from_asset('lambda'),
                                            function_name="start-textract")

        # Lambda Integration
        integration = apigateway.LambdaIntegration(trigger_textract)

        # Create Resource and Method
        resource = rest_api.root.add_resource("upload")
        method = resource.add_method("PUT", integration)     
        
        # Grant full access to S3 and Textract
        trigger_textract.add_to_role_policy(iam.PolicyStatement(
            actions=[
                's3:GetObject',
                's3:PutObject',
                's3:ListBucket',
                's3:DeleteObject',
                'textract:*',
                'comprehend:*',
                'rekognition:*'
            ],
            resources=['*']  # This allows access to all S3 buckets and Textract resources
        ))

        # Add Trigger and Environment Variables
        trigger_textract.add_event_source(eventsources.S3EventSource(self.input_bucket, events=[s3.EventType.OBJECT_CREATED]))
        
        # Create the queue
        MySqsQueue = sqs.Queue(self, "MySqsQueue")

        # Create the Topic
        MySnsTopic = sns.Topic(self, "MySnsTopic")

        # Create an SQS topic subscription object
        sqsSubscription = snssubs.SqsSubscription(MySqsQueue)

        # Add the SQS subscription to the sns topic
        MySnsTopic.add_subscription(sqsSubscription)

        # Define the condition
        condition = {
            'ArnEquals': {
                'aws:SourceArn': MySnsTopic.topic_arn
                }
        }

        # Add policy statement to SQS Policy that is created as part of the new queue
        iam.PolicyStatement(actions=['SQS:SendMessage'],
                            effect=iam.Effect.ALLOW,
                            conditions=condition,
                            resources=[MySqsQueue.queue_arn],
                            principals=[
                                iam.ServicePrincipal('sns.amazonaws.com')
                            ]
                            )

        CfnOutput(self, "SQS queue name", description="SQS queue name", value=MySqsQueue.queue_name)
        CfnOutput(self, "SQS queue ARN", description="SQS queue arn", value=MySqsQueue.queue_arn)
        CfnOutput(self, "SQS queue URL", description="SQS queue URL", value=MySqsQueue.queue_url)
        CfnOutput(self, "SNS topic name", description="SNS topic name", value=MySnsTopic.topic_name)
        CfnOutput(self, "SNS topic ARN", description="SNS topic ARN", value=MySnsTopic.topic_arn)

app = App()
CdklambdaStack(app, "CdklambdaStack")
app.synth()
