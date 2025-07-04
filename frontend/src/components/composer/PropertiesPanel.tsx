import React, { useEffect } from 'react';
import { Form, Input, Typography, Button, Space, InputNumber, Select } from 'antd';
import { MinusCircleOutlined, PlusOutlined } from '@ant-design/icons';
import { ComposerComponent } from '../../pages/VisualComposerPage'; // Import the extended type

const { Title, Text } = Typography;
const { Option } = Select;

interface PropertiesPanelProps {
  component: ComposerComponent | null; // Can be null if no component is selected
  onUpdateProperties: (id: string, newProperties: Record<string, any>) => void;
}

const PropertiesPanel: React.FC<PropertiesPanelProps> = ({ component, onUpdateProperties }) => {
  const [form] = Form.useForm();

  useEffect(() => {
    if (component) {
      form.setFieldsValue(component.properties);
    } else {
      form.resetFields();
    }
  }, [component, form]);

  if (!component) {
    return (
      <div style={{ padding: '16px' }}>
        <Title level={4} style={{ marginTop: 0, textAlign: 'center' }}>Properties</Title>
        <Text type="secondary">Select a component on the canvas to view and edit its properties.</Text>
      </div>
    );
  }

  const handleValuesChange = (_changedValues: any, allValues: any) => {
    // Filter out undefined values which can happen with Form.List remove operations
    const cleanedValues = { ...allValues };
    Object.keys(cleanedValues).forEach(key => {
      if (cleanedValues[key] === undefined && component.properties[key] !== undefined) {
        // If a field was cleared but existed, keep it as empty string or null based on type
        // For Form.List, removed items will be undefined.
        // This simple cleaner might not be perfect for all cases, esp. Form.List.
      }
      if (Array.isArray(cleanedValues[key])) {
        cleanedValues[key] = cleanedValues[key].filter(item => item !== undefined);
      }
    });
    onUpdateProperties(component.id, cleanedValues);
  };

  const renderCommonFields = () => (
    <>
      <Form.Item
        label="Component Name"
        name="displayName" // Using 'displayName' to avoid conflict with 'name' in tier structure
        rules={[{ required: true, message: 'Please input a name for the component!' }]}
      >
        <Input />
      </Form.Item>
    </>
  );

  const renderSpecificFields = () => {
    switch (component.type) {
      case 'AWS_EC2_INSTANCE':
        return (
          <>
            {renderCommonFields()}
            <Form.Item label="Instance Size" name="instance_size" rules={[{ required: true }]}>
              <Select>
                <Option value="t3.micro">t3.micro</Option>
                <Option value="t3.small">t3.small</Option>
                <Option value="t3.medium">t3.medium</Option>
                <Option value="m5.large">m5.large</Option>
              </Select>
            </Form.Item>
            <Form.Item label="AMI ID" name="ami_id" rules={[{ required: true }]}>
              <Input placeholder="ami-0abcdef123" />
            </Form.Item>
            <Form.List name="tags">
              {(fields, { add, remove }) => (
                <>
                  {fields.map(({ key, name, ...restField }) => (
                    <Space key={key} style={{ display: 'flex', marginBottom: 8 }} align="baseline">
                      <Form.Item
                        {...restField}
                        name={[name, 'key']}
                        rules={[{ required: true, message: 'Missing key' }]}
                        style={{width: '100px'}}
                      >
                        <Input placeholder="Key" />
                      </Form.Item>
                      <Form.Item
                        {...restField}
                        name={[name, 'value']}
                        rules={[{ required: true, message: 'Missing value' }]}
                         style={{width: '100px'}}
                      >
                        <Input placeholder="Value" />
                      </Form.Item>
                      <MinusCircleOutlined onClick={() => remove(name)} />
                    </Space>
                  ))}
                  <Form.Item>
                    <Button type="dashed" onClick={() => add()} block icon={<PlusOutlined />}>
                      Add Tag
                    </Button>
                  </Form.Item>
                </>
              )}
            </Form.List>
          </>
        );
      case 'OPENSTACK_VM':
        return (
          <>
            {renderCommonFields()}
            <Form.Item label="Flavor" name="flavor" rules={[{ required: true }]}>
              <Input placeholder="e.g., m1.small" />
            </Form.Item>
            <Form.Item label="Image ID" name="image_id" rules={[{ required: true }]}>
              <Input placeholder="UUID of Glance image" />
            </Form.Item>
            <Form.Item label="Network ID" name="network_id" rules={[{ required: true }]}>
              <Input placeholder="UUID of Neutron network" />
            </Form.Item>
          </>
        );
      case 'ANSIBLE_PLAYBOOK_TIER':
      case 'TERRAFORM_TIER':
        return (
          <>
            {renderCommonFields()}
            <Form.Item label="Git Repository URL" name="git_repo" rules={[{ required: true, type: 'url' }]}>
              <Input placeholder="https://github.com/user/repo.git" />
            </Form.Item>
            <Form.Item
              label={component.type === 'ANSIBLE_PLAYBOOK_TIER' ? "Playbook Path" : "Module Path"}
              name={component.type === 'ANSIBLE_PLAYBOOK_TIER' ? "playbook_path" : "path"}
              rules={[{ required: true }]}
            >
              <Input placeholder={component.type === 'ANSIBLE_PLAYBOOK_TIER' ? "e.g., site.yml" : "e.g., modules/webserver"} />
            </Form.Item>
            <Form.List name="variables">
              {(fields, { add, remove }) => (
                 <>
                  {fields.map(({ key, name, ...restField }) => (
                    <Space key={key} style={{ display: 'flex', marginBottom: 8 }} align="baseline">
                      <Form.Item {...restField} name={[name, 'key']} rules={[{ required: true, message: 'Missing key' }]}>
                        <Input placeholder="Var Key" />
                      </Form.Item>
                      <Form.Item {...restField} name={[name, 'value']} rules={[{ required: true, message: 'Missing value' }]}>
                        <Input placeholder="Var Value" />
                      </Form.Item>
                      <MinusCircleOutlined onClick={() => remove(name)} />
                    </Space>
                  ))}
                  <Form.Item>
                    <Button type="dashed" onClick={() => add({key: '', value: ''})} block icon={<PlusOutlined />}>
                      Add Variable
                    </Button>
                  </Form.Item>
                </>
              )}
            </Form.List>
          </>
        );
      default:
        return <Text>No specific properties defined for type: {component.type}</Text>;
    }
  };

  return (
    <div style={{ padding: '16px' }}>
      <Title level={4} style={{ marginTop: 0, marginBottom: 20, textAlign: 'center' }}>
        Properties: <span style={{color: '#1890ff'}}>{component.name || component.type.replace(/_/g, ' ')}</span>
      </Title>
      <Form
        form={form}
        layout="vertical"
        onValuesChange={handleValuesChange}
        initialValues={component.properties} // Set initial values when component changes
      >
        {renderSpecificFields()}
      </Form>
    </div>
  );
};

export default PropertiesPanel;
