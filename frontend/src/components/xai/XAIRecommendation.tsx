import React, { useState } from 'react';
import { Card, Typography, Button, Collapse, Space, Tag, Alert } from 'antd';
import { BulbOutlined, DownOutlined, RightOutlined, CheckCircleOutlined, WarningOutlined, InfoCircleOutlined } from '@ant-design/icons';

const { Text, Paragraph, Link: AntLink } = Typography;
const { Panel } = Collapse;

interface SupportingData {
  type: 'chart' | 'text' | 'log_event' | 'link';
  title: string;
  content?: string;
  imageUrl?: string;
  url?: string;
}

interface Evidence {
  reasoning: string;
  supportingData: SupportingData[];
}

interface ActionButton {
    label: string;
    onClick: ()_=> void;
    type?: "primary" | "ghost" | "dashed" | "link" | "text" | "default";
    danger?: boolean;
    icon?: React.ReactNode;
}

interface XAIRecommendationProps {
  insight: string;
  details?: string;
  evidence: Evidence;
  severity?: 'critical' | 'high' | 'medium' | 'low' | 'info'; // For styling
  defaultActions?: ActionButton[];
}

const XAIRecommendation: React.FC<XAIRecommendationProps> = ({
  insight,
  details,
  evidence,
  severity = 'info',
  defaultActions = []
}) => {
  const [showEvidence, setShowEvidence] = useState(false);

  const getSeverityProperties = () => {
    switch (severity) {
      case 'critical':
        return { icon: <WarningOutlined style={{color: 'red'}}/>, color: "red", alertType: "error" as const };
      case 'high':
        return { icon: <WarningOutlined style={{color: 'orange'}}/>, color: "orange", alertType: "warning" as const };
      case 'medium':
        return { icon: <InfoCircleOutlined style={{color: 'gold'}}/>, color: "gold", alertType: "warning" as const };
      case 'low':
        return { icon: <InfoCircleOutlined style={{color: 'blue'}}/>, color: "blue", alertType: "info" as const };
      default: // info
        return { icon: <BulbOutlined style={{color: 'green'}}/>, color: "green", alertType: "success" as const };
    }
  };

  const severityProps = getSeverityProperties();

  return (
    <Card
        title={
            <Space>
                {severityProps.icon}
                <Text strong>{insight}</Text>
            </Space>
        }
        bordered={true}
        style={{ marginBottom: 16, boxShadow: '0 2px 8px rgba(0, 0, 0, 0.09)' }}
        headStyle={{borderBottom: `2px solid ${severityProps.color}`}}
    >
      {details && <Paragraph type="secondary">{details}</Paragraph>}

      <Space style={{marginTop: defaultActions.length > 0 ? 8 : 0, marginBottom: 8, display: 'flex', justifyContent: 'space-between'}}>
        <Button type="link" onClick={() => setShowEvidence(!showEvidence)} style={{ paddingLeft: 0 }}>
          {showEvidence ? <><DownOutlined /> Hide Evidence</> : <><RightOutlined /> Show Evidence</>}
        </Button>
        <Space>
            {defaultActions.map(action => (
                <Button key={action.label} type={action.type || "default"} danger={action.danger} onClick={action.onClick} icon={action.icon}>
                    {action.label}
                </Button>
            ))}
        </Space>
      </Space>

      <Collapse activeKey={showEvidence ? ['1'] : []} bordered={false} ghost>
        <Panel header="" key="1" showArrow={false} style={{padding:0, border: 'none'}}>
          <div style={{paddingTop: 10, borderTop: '1px solid #f0f0f0'}}>
            <Text strong>Reasoning:</Text>
            <Paragraph style={{whiteSpace: 'pre-wrap'}}>{evidence.reasoning}</Paragraph>

            {evidence.supportingData && evidence.supportingData.length > 0 && (
              <>
                <Text strong>Supporting Data:</Text>
                {evidence.supportingData.map((data, index) => (
                  <Card key={index} size="small" style={{ marginTop: 8 }} title={data.title}>
                    {data.type === 'chart' && data.imageUrl && (
                      <img src={data.imageUrl} alt={data.title} style={{ maxWidth: '100%', borderRadius: '4px' }} />
                    )}
                    {data.type === 'text' && data.content && <Paragraph>{data.content}</Paragraph>}
                    {data.type === 'log_event' && data.content && <Tag color="blue" style={{whiteSpace: 'pre-wrap'}}>{data.content}</Tag>}
                    {data.type === 'link' && data.url && (
                      <AntLink href={data.url} target="_blank" rel="noopener noreferrer">
                        {data.content || data.url}
                      </AntLink>
                    )}
                  </Card>
                ))}
              </>
            )}
          </div>
        </Panel>
      </Collapse>
    </Card>
  );
};

export default XAIRecommendation;
