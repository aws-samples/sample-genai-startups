#!/usr/bin/env bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# Peer the hub-region TGW (us-east-2) with a remote-region TGW and add static routes both ways.
# TGW peering does not propagate routes, so every new leaf VPC needs a static route on the hub side.
# Usage: tgw-peer.sh <remote-region> <remote-vpc-cidr>
set -euo pipefail
HR=us-east-2; RR=$1; RCIDR=$2; HUBSIDE=10.200.0.0/14
tgw() { aws ec2 describe-transit-gateways --region $1 --filters Name=tag:project,Values=global-routing Name=state,Values=available \
  --query 'TransitGateways[0].[TransitGatewayId,Options.AssociationDefaultRouteTableId]' --output text; }
read HTGW HRT < <(tgw $HR); read RTGW RRT < <(tgw $RR)
ACCT=$(aws sts get-caller-identity --query Account --output text)

PA=$(aws ec2 describe-transit-gateway-peering-attachments --region $HR \
  --filters Name=transit-gateway-id,Values=$HTGW Name=state,Values=available,pendingAcceptance,pending,initiatingRequest \
  --query "TransitGatewayPeeringAttachments[?AccepterTgwInfo.TransitGatewayId=='$RTGW'].TransitGatewayAttachmentId | [0]" --output text)
if [[ "$PA" == "None" ]]; then
  PA=$(aws ec2 create-transit-gateway-peering-attachment --region $HR --transit-gateway-id $HTGW \
    --peer-transit-gateway-id $RTGW --peer-account-id $ACCT --peer-region $RR \
    --tag-specifications "ResourceType=transit-gateway-attachment,Tags=[{Key=project,Value=global-routing},{Key=Name,Value=use2-$RR}]" \
    --query TransitGatewayPeeringAttachment.TransitGatewayAttachmentId --output text)
fi
echo "peering $PA"
while :; do
  S=$(aws ec2 describe-transit-gateway-peering-attachments --region $RR --transit-gateway-attachment-ids $PA --query 'TransitGatewayPeeringAttachments[0].State' --output text 2>/dev/null || echo pending)
  [[ $S == available ]] && break
  [[ $S == pendingAcceptance ]] && aws ec2 accept-transit-gateway-peering-attachment --region $RR --transit-gateway-attachment-id $PA >/dev/null
  sleep 15
done
echo "peering available"
aws ec2 create-transit-gateway-route --region $HR --transit-gateway-route-table-id $HRT --destination-cidr-block $RCIDR --transit-gateway-attachment-id $PA >/dev/null 2>&1 || true
aws ec2 create-transit-gateway-route --region $RR --transit-gateway-route-table-id $RRT --destination-cidr-block $HUBSIDE --transit-gateway-attachment-id $PA >/dev/null 2>&1 || true
echo "static routes: $HR $RCIDR -> $PA ; $RR $HUBSIDE -> $PA"
