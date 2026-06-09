#!/usr/bin/env python3.12
"""Generate the AnyCompany Hotels architecture diagram (diagram-as-code).

Renders ``docs/img/architecture.png`` from the live shape of the platform so the
README diagram stays accurate and reproducible. Run it whenever the architecture
changes rather than hand-editing an image.

Requirements:
    brew install graphviz          # system dependency (the `dot` binary)
    pip install diagrams           # pip package (this script)

Usage:
    python3.12 scripts/generate_architecture_diagram.py
"""

from diagrams import Diagram, Cluster, Edge
from diagrams.aws.analytics import Athena, KinesisDataFirehose
from diagrams.aws.compute import Lambda
from diagrams.aws.database import Aurora, RDS
from diagrams.aws.integration import Eventbridge, SQS, StepFunctions
from diagrams.aws.network import APIGateway, CloudFront
from diagrams.aws.security import Cognito, WAF
from diagrams.aws.storage import S3
from diagrams.onprem.client import Users

# Output to docs/img/architecture(.png). `filename` is extension-less; the
# outformat appends .png. show=False so it doesn't try to open a viewer.
# Wider, well-spaced canvas. nodesep/ranksep open up the layout so multi-line
# labels don't crowd; LR keeps the request flow left-to-right and lands a
# landscape image that reads well in the README.
GRAPH_ATTR = {
    "fontsize": "22",
    "bgcolor": "white",
    "pad": "0.6",
    "nodesep": "0.6",
    "ranksep": "1.4",
    "splines": "spline",
}

with Diagram(
    "AnyCompany Hotels & Resorts — Serverless Hospitality Platform",
    filename="docs/img/architecture",
    outformat="png",
    show=False,
    direction="LR",
    graph_attr=GRAPH_ATTR,
):
    with Cluster("Clients"):
        guests = Users("Guests")
        staff = Users("Staff")

    # Cross-cutting security controls.
    waf = WAF("WAF\n(CloudFront + regional)")
    cognito = Cognito("Cognito\nuser pool")

    with Cluster("Guest Channels (CloudFront + S3)"):
        crs_fe = CloudFront("CRS Frontend\n(React)")
        pms_fe = CloudFront("PMS Frontend\n(React)")

    with Cluster("Distribution & Access (REST API Gateway + JWT)"):
        crs_api = APIGateway("CRS API")
        pms_api = APIGateway("PMS API")

    # Compute layer split into its three real groupings so the row balances
    # instead of collapsing into one oversized node.
    with Cluster("Core Services (Lambda · Python 3.12 · arm64)"):
        crs_fn = Lambda("CRS · Booking\nPayment")
        pms_fn = Lambda("PMS · Check-in/out\nHousekeeping · Billing\nLoyalty · Night Audit")
        worker_fn = Lambda("Event consumers\n+ workflow actions")

    with Cluster("Data"):
        proxy = RDS("RDS Proxy\n(IAM auth)")
        aurora = Aurora("Aurora Serverless v2\nPostgreSQL")
        proxy >> Edge(style="bold") >> aurora

    with Cluster("Async Processing"):
        bus = Eventbridge("EventBridge\nanycompany-events")
        sqs = SQS("SQS consumers\nbilling · housekeeping\nloyalty · notifications")
        sfn = StepFunctions("Step Functions\nCheckoutBilling\nHousekeepingDispatch")

    with Cluster("Analytics"):
        firehose = KinesisDataFirehose("Firehose")
        lake = S3("S3 (Parquet)")
        athena = Athena("Athena")
        firehose >> lake >> athena

    # Request path: users -> CloudFront -> API -> Lambda.
    guests >> Edge(color="darkgreen") >> crs_fe >> crs_api >> crs_fn
    staff >> Edge(color="darkblue") >> pms_fe >> pms_api >> pms_fn

    # Cross-cutting: WAF guards the frontends, Cognito authorizes the APIs.
    waf >> Edge(style="dotted", color="firebrick") >> [crs_fe, pms_fe]
    cognito >> Edge(style="dotted", color="darkorange") >> [crs_api, pms_api]

    # Data access from the request-path Lambdas.
    crs_fn >> Edge(style="bold") >> proxy
    pms_fn >> Edge(style="bold") >> proxy

    # Events: request Lambdas publish; consumers + workflows process; workflows
    # emit follow-on events (e.g. billing.payment_processed).
    crs_fn >> bus
    pms_fn >> bus
    bus >> sqs >> Edge(style="dashed") >> worker_fn >> sfn
    worker_fn >> Edge(style="bold") >> proxy
    sfn >> Edge(style="dashed", color="dimgray") >> bus

    # Analytics ingestion.
    pms_fn >> Edge(style="dashed", color="gray") >> firehose
