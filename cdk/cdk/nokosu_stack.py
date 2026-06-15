from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    CfnOutput,
)
from constructs import Construct


class NokosuStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # VPC（デフォルトVPCを使用）
        vpc = ec2.Vpc.from_lookup(self, "DefaultVpc", is_default=True)

        # Security Group
        sg = ec2.SecurityGroup(
            self, "NokosuSG",
            vpc=vpc,
            description="Nokosu security group",
            allow_all_outbound=True,
        )
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(22),   "SSH")
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80),   "HTTP")
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(443),  "HTTPS")
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(5001), "Flask dev")

        # IAM Role（SSM接続 + Secrets Manager読み取り）
        role = iam.Role(
            self, "NokosuEC2Role",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                )
            ]
        )
        # fx-diaryと同じSecrets Managerのキーを読み取る権限
        role.add_to_policy(iam.PolicyStatement(
            actions=["secretsmanager:GetSecretValue"],
            resources=[
                f"arn:aws:secretsmanager:ap-northeast-1:{self.account}:secret:fx-diary/anthropic-api-key*"
            ]
        ))

        # S3権限（DBバックアップのエクスポート/インポート用）
        role.add_to_policy(iam.PolicyStatement(
            actions=[
                "s3:GetObject",
                "s3:PutObject",
                "s3:DeleteObject",
                "s3:ListBucket",
            ],
            resources=[
                "arn:aws:s3:::fxdiarystack-chartbucket871feb42-brlffpq6m4kz",
                "arn:aws:s3:::fxdiarystack-chartbucket871feb42-brlffpq6m4kz/*",
            ]
        ))

        # User Data（起動時に自動セットアップ）
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            # 基本セットアップ
            "apt-get update -y",
            "apt-get install -y python3 python3-pip python3-venv nginx git",

            # GitHubからクローン（publicリポジトリ）
            "git clone https://github.com/Haze201808/nokosu.git /opt/nokosu",

            # データディレクトリ作成
            "mkdir -p /opt/nokosu/data",

            # clone後にubuntuユーザーに権限付与
            "chown -R ubuntu:ubuntu /opt/nokosu",

            # 仮想環境 & 依存関係インストール
            "python3 -m venv /opt/nokosu/.venv",
            "/opt/nokosu/.venv/bin/pip install -r /opt/nokosu/requirements.txt",
            "/opt/nokosu/.venv/bin/pip install gunicorn boto3 anthropic",

            # .env作成
            "echo 'DATABASE_URL=sqlite:////opt/nokosu/data/nokosu.db' > /opt/nokosu/.env",
            "echo \"SECRET_KEY=$(openssl rand -hex 32)\" >> /opt/nokosu/.env",
            "echo 'ANTHROPIC_SECRET_NAME=fx-diary/anthropic-api-key' >> /opt/nokosu/.env",

            # nginx設定
            "cat > /etc/nginx/sites-available/nokosu << 'NGINXEOF'\n"
            "server {\n"
            "    listen 80;\n"
            "    server_name _;\n"
            "\n"
            "    location / {\n"
            "        proxy_pass http://127.0.0.1:5001;\n"
            "        proxy_set_header Host $host;\n"
            "        proxy_set_header X-Real-IP $remote_addr;\n"
            "    }\n"
            "}\n"
            "NGINXEOF",

            "ln -sf /etc/nginx/sites-available/nokosu /etc/nginx/sites-enabled/",
            "rm -f /etc/nginx/sites-enabled/default",
            "systemctl restart nginx",

            # systemdサービス登録
            "cat > /etc/systemd/system/nokosu.service << 'SVCEOF'\n"
            "[Unit]\n"
            "Description=Nokosu Flask App\n"
            "After=network.target\n"
            "\n"
            "[Service]\n"
            "User=ubuntu\n"
            "WorkingDirectory=/opt/nokosu\n"
            "EnvironmentFile=/opt/nokosu/.env\n"
            "ExecStart=/opt/nokosu/.venv/bin/gunicorn -w 2 -b 127.0.0.1:5001 app:app\n"
            "Restart=always\n"
            "\n"
            "[Install]\n"
            "WantedBy=multi-user.target\n"
            "SVCEOF",

            "systemctl daemon-reload",
            "systemctl enable nokosu",
            "systemctl start nokosu",
        )

        # EC2インスタンス
        instance = ec2.Instance(
            self, "NokosuInstance",
            instance_type=ec2.InstanceType("t3.micro"),
            machine_image=ec2.MachineImage.generic_linux({
                "ap-northeast-1": "ami-0d52744d6551d851e"  # Ubuntu 24.04 LTS (東京)
            }),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PUBLIC
            ),
            security_group=sg,
            role=role,
            user_data=user_data,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/sda1",
                    volume=ec2.BlockDeviceVolume.ebs(
                        volume_size=20,
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                    )
                )
            ]
        )

        # 出力
        CfnOutput(
            self, "NokosuURL",
            value=f"http://{instance.instance_public_ip}",
            description="Nokosu App URL",
        )
        CfnOutput(
            self, "InstanceId",
            value=instance.instance_id,
            description="EC2 Instance ID (for SSM connection)",
        )

