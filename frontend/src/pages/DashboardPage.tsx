import React from 'react';
import { Typography, Row, Col, Divider } from 'antd';
import XAIRecommendation from '../components/xai/XAIRecommendation';

const { Title, Paragraph } = Typography;

// Static data for XAI component examples
const xaiDataResize = {
  insight: "Recommendation: Resize VM web-prod-03 from t3.xlarge to t3.large.",
  details: "Projected monthly savings: $85.",
  evidence: {
    reasoning: "This VM's peak CPU utilization over the past 30 days has been 38%, which is below the 50% threshold defined in your 'Cost Optimization' policy. The t3.large instance type can support this workload while reducing costs.",
    supportingData: [
      { type: 'chart', title: 'CPU Utilization (web-prod-03, Last 30 Days)', imageUrl: 'https://via.placeholder.com/400x200.png?text=CPU+Utilization+Chart' }, // Placeholder image
      { type: 'text', title: 'Policy Reference', content: "Policy ID: COST-OPT-001 - VM CPU Threshold < 50% for 30 days." }
    ]
  }
};

const xaiDataLatency = {
  insight: "Critical Alert: Application checkout-api is experiencing high latency.",
  details: "Recommended Action: Roll back deployment v1.2.1.",
  evidence: {
    reasoning: "The latency spike for checkout-api directly correlates with the deployment of version v1.2.1. Retrieved logs from this deployment show a new database query being introduced. This query is performing a full table scan on a large table, which is the likely cause of the performance degradation. Rolling back to the previous stable version v1.2.0 is the recommended immediate action to restore service.",
    supportingData: [
      { type: 'chart', title: 'API P95 Latency (checkout-api)', imageUrl: 'https://via.placeholder.com/400x200.png?text=API+Latency+Chart' },
      { type: 'chart', title: 'Host CPU Utilization (checkout-pods)', imageUrl: 'https://via.placeholder.com/400x200.png?text=Host+CPU+Chart' },
      { type: 'log_event', title: 'Deployment Event', content: "Deployment v1.2.1 completed at 2023-03-15 10:30 UTC." }
    ]
  }
};


const DashboardPage: React.FC = () => {
  return (
    <div style={{ padding: '20px' }}>
      <Title level={2}>Operations Dashboard</Title>
      <Paragraph>
        Welcome to the Project Podi Dashboard. Here you will find key insights and AI-driven recommendations.
      </Paragraph>

      <Divider>AI Recommendations</Divider>

      <Row gutter={[16, 16]}>
        <Col xs={24} md={12} lg={8}>
          <XAIRecommendation
            insight={xaiDataResize.insight}
            details={xaiDataResize.details}
            evidence={xaiDataResize.evidence}
            defaultActions={[{label: "Execute Resize", onClick: () => alert("Execute Resize Clicked (Not Implemented)")}, {label: "Dismiss", onClick: () => alert("Dismiss Clicked")}]}
          />
        </Col>
        <Col xs={24} md={12} lg={8}>
          <XAIRecommendation
            insight={xaiDataLatency.insight}
            details={xaiDataLatency.details}
            evidence={xaiDataLatency.evidence}
            defaultActions={[{label: "Initiate Rollback", type: "primary", danger: true, onClick: () => alert("Rollback Clicked (Not Implemented)")}, {label: "Acknowledge", onClick: () => alert("Acknowledge Clicked")}]}
          />
        </Col>
         <Col xs={24} md={12} lg={8}>
          <XAIRecommendation
            insight="Information: New Kubernetes version v1.28.2 is available for cluster 'prod-us-east-1'."
            details="Consider upgrading to benefit from the latest security patches and features."
            evidence={{
                reasoning: "Staying up-to-date with Kubernetes versions is crucial for security and stability. Version v1.28.2 includes patches for several CVEs and performance improvements.",
                supportingData: [
                    {type: 'link', title: 'K8s v1.28.2 Changelog', url: 'https://github.com/kubernetes/kubernetes/blob/master/CHANGELOG/CHANGELOG-1.28.md#v1282'},
                    {type: 'text', title: 'Current Cluster Version', content: 'v1.27.5'}
                ]
            }}
            defaultActions={[{label: "Schedule Upgrade", onClick: () => alert("Schedule Upgrade Clicked")}, {label: "More Info", onClick: () => alert("More Info Clicked")}]}
          />
        </Col>
      </Row>

      {/* Other dashboard widgets can be added here */}

    </div>
  );
};

export default DashboardPage;
