import { useState, useEffect } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Button, Dropdown, Avatar, Space, Drawer, Badge } from 'antd'
import {
  HomeOutlined, DeleteOutlined, ShareAltOutlined, SettingOutlined,
  UserOutlined, LogoutOutlined, ToolOutlined, BulbOutlined, BulbFilled, MenuOutlined,
} from '@ant-design/icons'
import { useAuth } from '../store/auth'
import { useTheme } from '../store/theme'

const { Header, Sider, Content } = Layout

export default function MainLayout() {
  const { user, logout } = useAuth()
  const { mode, toggle: toggleTheme } = useTheme()
  const navigate = useNavigate()
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768)
  const [trashCount, setTrashCount] = useState(0)

  // 定期获取回收站数量
  useEffect(() => {
    const fetch = () => {
      const token = localStorage.getItem('token')
      if (!token) return
      window.fetch('/api/v1/files/trash/stats', { headers: { Authorization: `Bearer ${token}` } })
        .then(r => r.json()).then(r => setTrashCount(r.data?.total_items || 0)).catch(() => {})
    }
    fetch()
    const timer = setInterval(fetch, 60000)  // 每60秒刷新
    return () => clearInterval(timer)
  }, [location.pathname])

  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth < 768)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const menuItems = [
    { key: '/', icon: <HomeOutlined />, label: '我的文件' },
    { key: '/recycle', icon: <DeleteOutlined />, label: trashCount > 0 ? <Badge count={trashCount} size="small" offset={[8, 0]}>回收站</Badge> : '回收站' },
    { key: '/share', icon: <ShareAltOutlined />, label: '我的分享' },
    { key: '/settings', icon: <ToolOutlined />, label: '个人设置' },
    ...(user?.role === 'admin'
      ? [{ key: '/admin', icon: <SettingOutlined />, label: '管理后台' }]
      : []),
  ]

  const userMenu = {
    items: [
      { key: 'info', label: `${user?.username} (${user?.role === 'admin' ? '管理员' : '用户'})`, disabled: true },
      { type: 'divider' as const },
      { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', danger: true },
    ],
    onClick: ({ key }: { key: string }) => {
      if (key === 'logout') {
        logout()
        navigate('/login')
      }
    },
  }

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '不限制'
    if (bytes < 1024) return bytes + ' B'
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB'
    if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB'
    return (bytes / 1073741824).toFixed(2) + ' GB'
  }

  const sidebarContent = (
    <>
      <div style={{ height: 48, margin: 16, color: '#fff', textAlign: 'center', fontWeight: 'bold', fontSize: 18 }}>
        ☁ CloudDisk
      </div>
      <Menu
        theme="dark"
        mode="inline"
        selectedKeys={[location.pathname]}
        items={menuItems}
        onClick={({ key }) => { navigate(key); setMobileMenuOpen(false) }}
      />
    </>
  )

  return (
    <Layout style={{ minHeight: '100vh' }}>
      {isMobile ? (
        <Drawer
          open={mobileMenuOpen}
          onClose={() => setMobileMenuOpen(false)}
          placement="left"
          width={240}
          styles={{ body: { padding: 0, background: '#001529' } }}
          closeIcon={null}
        >
          {sidebarContent}
        </Drawer>
      ) : (
        <Sider collapsible collapsed={collapsed} onCollapse={setCollapsed} theme="dark">
          {sidebarContent}
        </Sider>
      )}
      <Layout>
        <Header style={{ background: '#fff', padding: '0 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #f0f0f0' }}>
          {isMobile && (
            <Button type="text" icon={<MenuOutlined />} onClick={() => setMobileMenuOpen(true)} />
          )}
          <Space>
            <span style={{ color: '#666', fontSize: 13 }}>
              已用 {formatBytes(user?.storage_used || 0)}
              {user?.storage_quota ? ` / ${formatBytes(user.storage_quota)}` : ''}
            </span>
            <Button
              type="text"
              icon={mode === 'dark' ? <BulbFilled style={{ color: '#faad14' }} /> : <BulbOutlined />}
              onClick={toggleTheme}
            />
            <Dropdown menu={userMenu} placement="bottomRight">
              <Button type="text" icon={<Avatar size="small" icon={<UserOutlined />} />}>
                {user?.username}
              </Button>
            </Dropdown>
          </Space>
        </Header>
        <Content style={{ margin: 16, padding: 24, background: '#fff', borderRadius: 8, minHeight: 360 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
