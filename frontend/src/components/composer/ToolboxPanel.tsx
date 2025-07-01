import React from 'react';
import { Typography, Card, List } from 'antd';
import { useDrag } from 'react-dnd'; // Will install react-dnd later
import { CloudServerOutlined, CodeOutlined, DatabaseOutlined, ApiOutlined, DeploymentUnitOutlined } from '@ant-design/icons';

const { Title, Text } = Typography;

export interface ToolboxItemType {
  type: string;
  name: string;
  icon?: React.ReactNode;
  description?: string;
}

const toolboxItems: ToolboxItemType[] = [
  { type: 'AWS_EC2_INSTANCE', name: 'AWS EC2 Instance', icon: <CloudServerOutlined />, description: "Virtual server in AWS." },
  { type: 'OPENSTACK_VM', name: 'OpenStack VM', icon: <CloudServerOutlined />, description: "Virtual server in OpenStack." },
  // { type: 'KVM_VM', name: 'KVM VM', icon: <CloudServerOutlined />, description: "Virtual server on KVM." }, // Add if needed
  { type: 'S3_BUCKET', name: 'S3 Bucket', icon: <DatabaseOutlined />, description: "Scalable object storage in AWS." },
  // { type: 'EBS_VOLUME', name: 'EBS Volume', icon: <DatabaseOutlined />, description: "Block storage for EC2." },
  // { type: 'VPC_NETWORK', name: 'VPC Network', icon: <ApiOutlined />, description: "Isolated virtual network." },
  // { type: 'LOAD_BALANCER', name: 'Load Balancer', icon: <DeploymentUnitOutlined />, description: "Distributes traffic." },
  { type: 'TERRAFORM_TIER', name: 'Terraform Tier', icon: <CodeOutlined />, description: "Infrastructure managed by Terraform." },
  { type: 'ANSIBLE_PLAYBOOK_TIER', name: 'Ansible Playbook Tier', icon: <CodeOutlined />, description: "Configuration by Ansible." },
  // { type: 'CUSTOM_BLUEPRINT_3TIER', name: '3-Tier Web App', icon: <DeploymentUnitOutlined />, description: "Predefined 3-tier application." },
];

const DraggableToolboxItem: React.FC<{ item: ToolboxItemType }> = ({ item }) => {
  const [{ isDragging }, drag] = useDrag(() => ({
    type: 'CANVAS_COMPONENT', // Unique type for dnd context
    item: { type: item.type, name: item.name }, // Data passed on drop
    collect: (monitor) => ({
      isDragging: !!monitor.isDragging(),
    }),
  }));

  return (
    <div ref={drag} style={{ opacity: isDragging ? 0.5 : 1, cursor: 'move' }}>
      <Card hoverable size="small" style={{ marginBottom: 8 }}>
        <Card.Meta
          avatar={item.icon || <DeploymentUnitOutlined />}
          title={<Text strong>{item.name}</Text>}
          description={item.description || item.type}
        />
      </Card>
    </div>
  );
};

const ToolboxPanel: React.FC = () => {
  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Title level={4} style={{ marginTop: 0, marginBottom: 16, textAlign: 'center' }}>Component Toolbox</Title>
      {/* <Input placeholder="Search Components..." style={{ marginBottom: 16 }} /> */}
      <div style={{ flexGrow: 1, overflowY: 'auto' }}>
        <List
            itemLayout="vertical"
            dataSource={toolboxItems}
            renderItem={(item) => (
              <List.Item style={{padding: '0px 0px 8px 0px', borderBlockEnd: 'none'}}>
                <DraggableToolboxItem item={item} />
              </List.Item>
            )}
          />
      </div>
    </div>
  );
};

export default ToolboxPanel;
