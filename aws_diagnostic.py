"""Safe, opt-in AWS diagnostic CLI. It reports types of failures, not secrets."""

import argparse


def main():
    parser = argparse.ArgumentParser(description="AEGIS AWS read-only diagnostics")
    parser.add_argument("--region", default="us-east-2")
    parser.add_argument("--bucket", help="Optional bucket name to test list permission")
    args = parser.parse_args()
    import boto3
    session = boto3.Session(region_name=args.region)
    print(f"AWS credentials resolved: {bool(session.get_credentials())}")
    print(f"Region configured: {args.region}")
    if args.bucket:
        try:
            session.client("s3").list_objects_v2(Bucket=args.bucket, Prefix="documents/", MaxKeys=1)
            print("S3 list permission: available")
        except Exception as exc:
            print(f"S3 list permission: unavailable ({type(exc).__name__})")


if __name__ == "__main__":
    main()
