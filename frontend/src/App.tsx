import React from 'react';
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import { Layout, Menu } from 'antd';
import { DndProvider } from 'react-dnd';
import { HTML5Backend } from 'react-dnd-html5-backend';
import './App.css';
import VisualComposerPage from './pages/VisualComposerPage';
import DashboardPage from './pages/DashboardPage';

const { Header, Content, Footer } = Layout;

const App: React.FC = () => {
  return (
    <DndProvider backend={HTML5Backend}> {/* Wrap with DndProvider */}
      <Router>
        <Layout className="layout" style={{ minHeight: '100vh' }}>
          <Header>
            <div className="logo" style={{ float: 'left', color: 'white', marginRight: '20px' }}>Project Podi</div>
            <Menu theme="dark" mode="horizontal" defaultSelectedKeys={['1']}>
              <Menu.Item key="1">
                <Link to="/">Visual Composer</Link>
              </Menu.Item>
              <Menu.Item key="2">
                <Link to="/dashboard">Dashboard (XAI)</Link>
              </Menu.Item>
            </Menu>
          </Header>
          <Content style={{ padding: '0', marginTop: '0', flexGrow: 1, display: 'flex', flexDirection: 'column' }}>
            {/* Removed default padding from Content to allow VisualComposerPage to take full height */}
            <div className="site-layout-content" style={{ background: '#fff', flexGrow: 1, display: 'flex', flexDirection: 'column' }}>
              <Routes>
                <Route path="/" element={<VisualComposerPage />} />
                <Route path="/dashboard" element={<DashboardPage />} />
              </Routes>
            </div>
          </Content>
          <Footer style={{ textAlign: 'center' }}>Project Podi ©2024 - AI-Driven Hybrid Cloud Management</Footer>
        </Layout>
      </Router>
    </DndProvider>
  );
};

export default App;
