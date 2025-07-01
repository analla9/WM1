import React, { useState, useCallback } from 'react';
import { Layout, Button, message, Row, Col } from 'antd';
import ToolboxPanel from '../components/composer/ToolboxPanel';
import CanvasPanel, { CanvasComponentData } from '../components/composer/CanvasPanel';
import PropertiesPanel from '../components/composer/PropertiesPanel';
import axios from 'axios'; // For API calls
import yaml from 'js-yaml'; // For converting JS object to YAML string

const { Sider, Content } = Layout;

export interface ComposerComponent extends CanvasComponentData {
  // Properties will be specific to the component type
  properties: Record<string, any>;
}


const VisualComposerPage: React.FC = () => {
  const [canvasComponents, setCanvasComponents] = useState<ComposerComponent[]>([]);
  const [selectedComponentId, setSelectedComponentId] = useState<string | null>(null);

  const handleDrop = (item: { type: string; name: string }, monitorPosition: { x: number; y: number }) => {
    const newComponent: ComposerComponent = {
      id: `comp_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`, // More robust ID
      type: item.type,
      name: item.name, // Use the display name from toolbox item
      x: monitorPosition.x - 250, // Adjust for toolbox width if needed and canvas offset
      y: monitorPosition.y - 64,  // Adjust for header height if needed and canvas offset
      properties: getDefaultProperties(item.type),
    };
    setCanvasComponents((prev) => [...prev, newComponent]);
  };

  const getDefaultProperties = (type: string): Record<string, any> => {
    // Define default properties for each component type
    switch (type) {
      case 'AWS_EC2_INSTANCE':
        return { instance_size: 't3.medium', ami_id: 'ami-0abcdef1234567890', tags: [{ key: 'Name', value: 'my-ec2' }] };
      case 'OPENSTACK_VM':
        return { flavor: 'm1.small', image_id: 'img-0123', network_id: 'net-private' };
      case 'ANSIBLE_PLAYBOOK_TIER':
        return { git_repo: 'https://example.com/ansible.git', playbook_path: 'site.yml', variables: [] };
      case 'TERRAFORM_TIER':
        return { git_repo: 'https://example.com/terraform.git', path: 'modules/webserver', variables: [] };
      default:
        return { name: 'Unnamed Component' };
    }
  };

  const handleSelectComponent = (id: string | null) => {
    setSelectedComponentId(id);
  };

  const handleUpdateComponentProperties = (id: string, newProperties: Record<string, any>) => {
    setCanvasComponents((prev) =>
      prev.map((comp) =>
        comp.id === id ? { ...comp, properties: newProperties } : comp
      )
    );
  };

  const selectedComponent = canvasComponents.find(comp => comp.id === selectedComponentId);

  const generateBlueprintYAML = (): string => {
    // Simplified YAML generation for Phase 5
    // Focuses on tiers based on canvas components
    const blueprintData = {
      apiVersion: 'cognitive-cmp.io/v1',
      kind: 'Blueprint',
      metadata: {
        name: `visual-bp-${Date.now()}`, // Dynamic name
        description: 'Blueprint generated from Visual Composer',
      },
      spec: {
        inputs: [], // For Phase 5, inputs are not dynamically generated from properties yet
        tiers: canvasComponents.map(comp => {
          let tierType = 'unknown';
          let source = undefined;
          let variables = { ...comp.properties }; // Start with all properties as variables

          // Basic mapping from visual component type to blueprint tier type
          if (comp.type === 'AWS_EC2_INSTANCE' || comp.type === 'OPENSTACK_VM' || comp.type === 'TERRAFORM_TIER') {
            tierType = 'terraform'; // Assume these are provisioned by Terraform
            if (comp.properties.git_repo) {
              source = { git: comp.properties.git_repo, path: comp.properties.path || '/' };
            }
          } else if (comp.type === 'ANSIBLE_PLAYBOOK_TIER') {
            tierType = 'ansible';
            if (comp.properties.git_repo) {
              source = { git: comp.properties.git_repo, path: comp.properties.playbook_path || '/' };
            }
          }

          // Remove structural properties from variables if they were used for source
          if (source) {
            delete variables.git_repo;
            delete variables.path;
            delete variables.playbook_path;
          }


          return {
            name: comp.name.toLowerCase().replace(/\s+/g, '-') + '-' + comp.id.substring(0,5), // e.g., aws-ec2-instance-comp_1
            type: tierType,
            source: source, // Simplified source for Phase 5
            variables: variables, // Pass all properties as variables for now
          };
        }),
        dependencies: [], // Connections not implemented in Phase 5
        lifecycle_actions: {},
      },
    };

    try {
      return yaml.dump(blueprintData);
    } catch (e) {
      console.error("Error generating YAML:", e);
      message.error("Failed to generate Blueprint YAML.");
      return "";
    }
  };

  const handleDeploy = async () => {
    const yamlBlueprint = generateBlueprintYAML();
    if (!yamlBlueprint) return;

    message.loading({ content: 'Deploying blueprint...', key: 'deploy' });
    console.log("Generated Blueprint YAML for deployment:\n", yamlBlueprint);

    try {
      // Use a placeholder blueprint_id for Phase 5
      const blueprintId = `visual-bp-${Date.now()}`;
      // API Gateway expects a JSON payload with a 'blueprint_yaml' field
      const payload = { blueprint_yaml: yamlBlueprint };

      await axios.post(`/api/v1/blueprints/${blueprintId}/deploy`, payload, {
        headers: { 'Content-Type': 'application/json' }
      });
      message.success({ content: `Blueprint '${blueprintId}' deployment request submitted!`, key: 'deploy', duration: 5 });
    } catch (error) {
      console.error('Deployment error:', error);
      let errorMessage = 'Failed to submit blueprint deployment request.';
      if (axios.isAxiosError(error) && error.response) {
        errorMessage += ` Server responded with ${error.response.status}: ${JSON.stringify(error.response.data)}`;
      }
      message.error({ content: errorMessage, key: 'deploy', duration: 5 });
    }
  };


  return (
    <Layout style={{ height: '100%', overflow: 'hidden' }}>
      <Sider width={250} theme="light" style={{ padding: '10px', borderRight: '1px solid #f0f0f0', overflowY: 'auto' }}>
        <ToolboxPanel />
      </Sider>
      <Layout style={{ display: 'flex', flexDirection: 'column' }}>
        <Content style={{ flexGrow: 1, position: 'relative' /* For positioning canvas items */ }}>
          <CanvasPanel
            components={canvasComponents}
            onDrop={handleDrop}
            onSelectComponent={handleSelectComponent}
            selectedComponentId={selectedComponentId}
          />
        </Content>
        <Row justify="end" style={{ padding: '10px', borderTop: '1px solid #f0f0f0', background: '#fff' }}>
          <Col>
            {/* <Button style={{ marginRight: 8 }}>Validate Blueprint</Button> */}
            {/* <Button style={{ marginRight: 8 }}>Save Blueprint</Button> */}
            <Button type="primary" onClick={handleDeploy} disabled={canvasComponents.length === 0}>
              Deploy Blueprint
            </Button>
          </Col>
        </Row>
      </Layout>
      {selectedComponent && (
        <Sider width={300} theme="light" style={{ padding: '10px', borderLeft: '1px solid #f0f0f0', overflowY: 'auto' }}>
          <PropertiesPanel
            component={selectedComponent}
            onUpdateProperties={handleUpdateComponentProperties}
          />
        </Sider>
      )}
    </Layout>
  );
};

export default VisualComposerPage;
