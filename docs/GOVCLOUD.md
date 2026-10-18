# GovCloud compatibility considerations

GovCloud is a separate AWS partition and account context. A commercial-region
IAM policy, ARN, endpoint, model-access grant, or quota result must not be
assumed to apply in GovCloud.

Before any GovCloud work, separately verify account eligibility, region and
service availability, `aws-us-gov` ARN partitioning, Bedrock model availability,
runtime endpoints, IAM permissions, logging, data residency, and compliance
requirements. This repository contains design guidance only; it does not claim
GovCloud deployment, authorization, or compliance certification.
