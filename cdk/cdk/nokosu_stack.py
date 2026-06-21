from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    CfnOutput,
    RemovalPolicy,
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
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80),   "HTTP (redirects to HTTPS)")
        sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(443),  "HTTPS")
        # 22(SSH)はSSM経由でアクセスするため開放不要
        # 5001(Flask dev)はnginxが127.0.0.1経由でプロキシするため外部公開不要

        # IAM Role（SSM接続用 - SSH鍵なしでもアクセス可能）
        role = iam.Role(
            self, "NokosuEC2Role",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                )
            ]
        )

        # User Data（起動時に自動セットアップ）
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            # 基本セットアップ
            "apt-get update -y",
            "apt-get install -y python3 python3-pip python3-venv nginx git",

            # アプリディレクトリ
            "mkdir -p /opt/nokosu",
            "cd /opt/nokosu",

            # GitHubからクローン（後でURLを差し替え）
            "git clone https://github.com/Haze201808/nokosu.git /opt/nokosu",

            # 仮想環境 & 依存関係インストール
            "python3 -m venv /opt/nokosu/.venv",
            "/opt/nokosu/.venv/bin/pip install -r /opt/nokosu/requirements.txt",
            "/opt/nokosu/.venv/bin/pip install gunicorn",

            # .env作成
            "echo 'DATABASE_URL=sqlite:////opt/nokosu/data/nokosu.db' > /opt/nokosu/.env",
            "echo 'SECRET_KEY=$(openssl rand -hex 32)' >> /opt/nokosu/.env",

            # データディレクトリ（SQLiteファイル置き場）
            "mkdir -p /opt/nokosu/data",

            # systemdサービス登録
            "cat > /etc/systemd/system/nokosu.service << 'EOF'\n"
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
            "EOF",

            "systemctl daemon-reload",
            "systemctl enable nokosu",
            "systemctl start nokosu",

            # nginx設定
            "cat > /etc/nginx/sites-available/nokosu << 'EOF'\n"
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
            "EOF",

            "ln -sf /etc/nginx/sites-available/nokosu /etc/nginx/sites-enabled/",
            "rm -f /etc/nginx/sites-enabled/default",
            "systemctl restart nginx",
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
                        volume_size=20,  # 20GB（SQLite余裕持って）
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                    )
                )
            ]
        )

        # Elastic IP（CDKコードで管理し、デプロイの度にIPが変わらないようにする）
        eip = ec2.CfnEIP(self, "NokosuEIP", domain="vpc")
        ec2.CfnEIPAssociation(
            self, "NokosuEIPAssociation",
            eip=eip.ref,
            instance_id=instance.instance_id,
        )

        # パブリックIPを出力（Elastic IPを参照。デプロイの度に変わらない）
        CfnOutput(
            self, "NokosuURL",
            value=f"https://nokosu.haze-lab.com (EIP: {eip.ref})",
            description="Nokosu App URL",
        )
        CfnOutput(
            self, "ElasticIP",
            value=eip.ref,
            description="Elastic IP address (固定IP・DNSのAレコードをここに向ける)",
        )
        CfnOutput(
            self, "InstanceId",
            value=instance.instance_id,
            description="EC2 Instance ID (for SSM connection)",
        )

