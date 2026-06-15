#!/usr/bin/env python3
import aws_cdk as cdk
from cdk.nokosu_stack import NokosuStack

app = cdk.App()

NokosuStack(
    app, "NokosuStack",
    env=cdk.Environment(
        account="447890741976",  # aws sts get-caller-identity で確認
        region="ap-northeast-1",
    )
)

app.synth()


