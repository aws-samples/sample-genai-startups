#!/usr/bin/env bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# Attach an EKS cluster's VPC to the region's Transit Gateway (creating the TGW if needed),
# route the whole test-bed range (10.200.0.0/14) via the TGW, and open the cluster SG to that range.
# Usage: tgw-attach.sh <cluster> <region>
set -euo pipefail
C=$1; R=$2; SUPER=10.200.0.0/14
TAGS="Key=project,Value=global-routing"

TGW=$(aws ec2 describe-transit-gateways --region $R \
  --filters Name=tag:project,Values=global-routing Name=state,Values=available,pending \
  --query 'TransitGateways[0].TransitGatewayId' --output text)
if [[ "$TGW" == "None" ]]; then
  TGW=$(aws ec2 create-transit-gateway --region $R --description "global-routing $R" \
    --options DefaultRouteTableAssociation=enable,DefaultRouteTablePropagation=enable,DnsSupport=enable \
    --tag-specifications "ResourceType=transit-gateway,Tags=[{$TAGS},{Key=Name,Value=gr-tgw-$R}]" \
    --query TransitGateway.TransitGatewayId --output text)
  echo "created $TGW"
fi
until [[ $(aws ec2 describe-transit-gateways --region $R --transit-gateway-ids $TGW --query 'TransitGateways[0].State' --output text) == available ]]; do sleep 15; done
echo "TGW $TGW available"

VPC=$(aws eks describe-cluster --region $R --name $C --query cluster.resourcesVpcConfig.vpcId --output text)
SG=$(aws eks describe-cluster --region $R --name $C --query cluster.resourcesVpcConfig.clusterSecurityGroupId --output text)
# one private subnet per AZ
SUBNETS=$(aws ec2 describe-subnets --region $R --filters Name=vpc-id,Values=$VPC Name=map-public-ip-on-launch,Values=false \
  --query 'Subnets[].SubnetId' --output text)

ATT=$(aws ec2 describe-transit-gateway-vpc-attachments --region $R \
  --filters Name=vpc-id,Values=$VPC Name=transit-gateway-id,Values=$TGW Name=state,Values=available,pending \
  --query 'TransitGatewayVpcAttachments[0].TransitGatewayAttachmentId' --output text)
if [[ "$ATT" == "None" ]]; then
  ATT=$(aws ec2 create-transit-gateway-vpc-attachment --region $R --transit-gateway-id $TGW --vpc-id $VPC \
    --subnet-ids $SUBNETS --tag-specifications "ResourceType=transit-gateway-attachment,Tags=[{$TAGS},{Key=Name,Value=$C}]" \
    --query TransitGatewayVpcAttachment.TransitGatewayAttachmentId --output text)
fi
until [[ $(aws ec2 describe-transit-gateway-vpc-attachments --region $R --transit-gateway-attachment-ids $ATT --query 'TransitGatewayVpcAttachments[0].State' --output text) == available ]]; do sleep 15; done
echo "attachment $ATT available"

for RT in $(aws ec2 describe-route-tables --region $R --filters Name=vpc-id,Values=$VPC --query 'RouteTables[].RouteTableId' --output text); do
  aws ec2 create-route --region $R --route-table-id $RT --destination-cidr-block $SUPER --transit-gateway-id $TGW >/dev/null 2>&1 \
    || aws ec2 replace-route --region $R --route-table-id $RT --destination-cidr-block $SUPER --transit-gateway-id $TGW
done
echo "routes $SUPER -> $TGW added"

aws ec2 authorize-security-group-ingress --region $R --group-id $SG \
  --ip-permissions "IpProtocol=-1,IpRanges=[{CidrIp=$SUPER,Description=global-routing-testbed}]" >/dev/null 2>&1 || true
echo "SG $SG open to $SUPER"
echo "$C $R VPC=$VPC TGW=$TGW ATT=$ATT SG=$SG"
