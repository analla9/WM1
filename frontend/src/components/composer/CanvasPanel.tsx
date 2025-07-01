import React from 'react';
import { useDrop, XYCoord } from 'react-dnd';
import { Card, Typography } from 'antd';
import { DeploymentUnitOutlined } from '@ant-design/icons'; // Default icon

const { Text } = Typography;

export interface CanvasComponentData {
  id: string;
  type: string;
  name: string;
  x: number;
  y: number;
  // properties will be part of ComposerComponent in VisualComposerPage
}

interface CanvasPanelProps {
  components: CanvasComponentData[];
  onDrop: (item: { type: string; name: string }, monitorPosition: XYCoord) => void;
  onSelectComponent: (id: string | null) => void;
  selectedComponentId: string | null;
}

const CanvasPanel: React.FC<CanvasPanelProps> = ({ components, onDrop, onSelectComponent, selectedComponentId }) => {
  const [{ isOver }, drop] = useDrop(() => ({
    accept: 'CANVAS_COMPONENT', // Must match the 'type' in DraggableToolboxItem
    drop: (item: { type: string; name: string }, monitor) => {
      const offset = monitor.getClientOffset(); // Get position where item was dropped
      if (offset) {
        onDrop(item, offset);
      }
    },
    collect: (monitor) => ({
      isOver: !!monitor.isOver(),
    }),
  }));

  const handleComponentClick = (event: React.MouseEvent, id: string) => {
    event.stopPropagation(); // Prevent canvas click if component is clicked
    onSelectComponent(id);
  };

  const handleCanvasClick = () => {
    onSelectComponent(null); // Deselect if canvas is clicked
  };

  return (
    <div
      ref={drop}
      onClick={handleCanvasClick}
      style={{
        position: 'relative', // Needed for absolute positioning of children
        width: '100%',
        height: '100%', // Make canvas take full available height
        backgroundColor: isOver ? '#e6f7ff' : '#f0f2f5', // Highlight when item is dragged over
        border: '1px dashed #91d5ff',
        overflow: 'auto', // In case components go out of bounds
        padding: '10px' // Some padding inside canvas
      }}
    >
      <Text type="secondary" style={{ position: 'absolute', top: 5, left: 10 }}>Drag components here to build your service.</Text>
      {components.map((comp) => (
        <Card
          key={comp.id}
          size="small"
          hoverable
          onClick={(e) => handleComponentClick(e, comp.id)}
          style={{
            position: 'absolute',
            left: comp.x,
            top: comp.y,
            width: 180, // Fixed width for now
            border: selectedComponentId === comp.id ? '2px solid #1890ff' : '1px solid #d9d9d9',
            boxShadow: selectedComponentId === comp.id ? '0 0 5px #1890ff' : 'none',
            cursor: 'pointer'
          }}
          bodyStyle={{ padding: '8px' }}
        >
          <Card.Meta
            avatar={<DeploymentUnitOutlined />} // Replace with type-specific icons later
            title={<Text strong ellipsis>{comp.name}</Text>}
            description={<Text type="secondary" ellipsis>Type: {comp.type.replace(/_/g, ' ')}</Text>}
          />
          {/* <Text style={{fontSize: '10px', color: 'gray'}}>ID: {comp.id.substring(0,8)}</Text> */}
        </Card>
      ))}
    </div>
  );
};

export default CanvasPanel;
