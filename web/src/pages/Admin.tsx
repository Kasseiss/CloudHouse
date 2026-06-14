import { useState, useEffect } from 'react'
import { Tabs, Table, Button, Modal, Input, InputNumber, Switch, Space, message, Tag, Popconfirm, Form, Empty, Card, Statistic, Row, Col, Progress } from 'antd'
import { UserAddOutlined, SettingOutlined, FileTextOutlined, DownloadOutlined, DashboardOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  getUsers, createUser, updateUserQuota, updateUserStatus, deleteUser,
  getSystemLogs, getSystemConfig, updateSystemConfig,
} from '../api/admin'
import dayjs from 'dayjs'

function UserManagement() {
  const [users, setUsers] = useState<any[]>([])
  const [loading, setLoading] = useState(false)

  const fetchUsers = async () => {
    setLoading(true)
    try {
      const res: any = await getUsers()
      setUsers(res.data?.items || res.data || [])
    } catch { /* handled */ }
    finally { setLoading(false) }
  }

  useEffect(() => { fetchUsers() }, [])

  const handleCreate = () => {
    let username = '', password = '', email = '', role = 'user'
    let quota = 1073741824
    Modal.confirm({
      title: '新建用户',
      width: 480,
      content: (
        <Space direction="vertical" style={{ width: '100%' }}>
          <Input placeholder="用户名" onChange={(e) => { username = e.target.value }} />
          <Input.Password placeholder="密码" onChange={(e) => { password = e.target.value }} />
          <Input placeholder="邮箱" onChange={(e) => { email = e.target.value }} />
          <Input placeholder="角色 (user/admin)" defaultValue="user" onChange={(e) => { role = e.target.value }} />
          <InputNumber style={{ width: '100%' }} placeholder="存储配额(字节)" defaultValue={1073741824} onChange={(v) => { quota = v || 1073741824 }} />
        </Space>
      ),
      onOk: async () => {
        await createUser({ username, password, email, role, storage_quota: quota })
        message.success('用户已创建')
        fetchUsers()
      },
    })
  }

  const handleQuota = (user: any) => {
    let quota = user.storage_quota
    Modal.confirm({
      title: `修改 ${user.username} 的存储配额`,
      content: <InputNumber style={{ width: '100%' }} defaultValue={quota} onChange={(v) => { quota = v || 0 }} />,
      onOk: async () => {
        await updateUserQuota(user.id, quota)
        message.success('配额已更新')
        fetchUsers()
      },
    })
  }

  const handleToggleStatus = async (user: any) => {
    await updateUserStatus(user.id, !user.is_active)
    message.success(`用户已${user.is_active ? '禁用' : '启用'}`)
    fetchUsers()
  }

  const handleDelete = async (id: number) => {
    await deleteUser(id)
    message.success('用户已删除')
    fetchUsers()
  }

  const columns: ColumnsType<any> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '用户名', dataIndex: 'username', key: 'username' },
    { title: '邮箱', dataIndex: 'email', key: 'email' },
    {
      title: '角色', dataIndex: 'role', key: 'role', width: 80,
      render: (r: string) => <Tag color={r === 'admin' ? 'red' : 'blue'}>{r}</Tag>,
    },
    { title: '状态', dataIndex: 'is_active', key: 'status', width: 80, render: (a: boolean) => a ? <Tag color="green">正常</Tag> : <Tag color="red">禁用</Tag> },
    { title: '已用/配额', key: 'storage', width: 160,
      render: (_, r) => `${(r.storage_used / 1073741824).toFixed(2)}GB / ${r.storage_quota ? (r.storage_quota / 1073741824).toFixed(2) + 'GB' : '不限'}` },
    { title: '创建时间', dataIndex: 'created_at', key: 'time', render: (t: string) => dayjs(t).format('YYYY-MM-DD'), width: 120 },
    {
      title: '操作', key: 'action', width: 280,
      render: (_, record) => (
        <Space>
          <Button size="small" onClick={() => handleQuota(record)}>配额</Button>
          <Popconfirm title={`确认${record.is_active ? '禁用' : '启用'}该用户？`} onConfirm={() => handleToggleStatus(record)}>
            <Button size="small" danger={record.is_active}>{record.is_active ? '禁用' : '启用'}</Button>
          </Popconfirm>
          <Popconfirm title="确认删除该用户？此操作不可恢复" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Button type="primary" icon={<UserAddOutlined />} onClick={handleCreate} style={{ marginBottom: 16 }}>新建用户</Button>
      <Table rowKey="id" columns={columns} dataSource={users} loading={loading} pagination={{ pageSize: 20 }}
        locale={{ emptyText: <Empty description="暂无用户" /> }} />
    </div>
  )
}

function SystemLogs() {
  const [logs, setLogs] = useState<any[]>([])
  const [loading, setLoading] = useState(false)

  const fetchLogs = async () => {
    setLoading(true)
    try {
      const res: any = await getSystemLogs({})
      setLogs(res.data?.items || res.data || [])
    } catch { /* handled */ }
    finally { setLoading(false) }
  }

  useEffect(() => { fetchLogs() }, [])

  const columns: ColumnsType<any> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '用户ID', dataIndex: 'user_id', key: 'uid', width: 80 },
    { title: '操作', dataIndex: 'action', key: 'action', render: (a: string) => <Tag>{a}</Tag>, width: 120 },
    { title: '详情', dataIndex: 'detail', key: 'detail' },
    { title: 'IP', dataIndex: 'ip_address', key: 'ip', width: 140 },
    { title: '时间', dataIndex: 'created_at', key: 'time', render: (t: string) => dayjs(t).format('YYYY-MM-DD HH:mm:ss'), width: 180 },
  ]

  return (
    <>
      <div style={{ marginBottom: 16 }}>
        <Button icon={<DownloadOutlined />} href="/api/v1/admin/logs/export" target="_blank">
          导出 CSV
        </Button>
      </div>
      <Table rowKey="id" columns={columns} dataSource={logs} loading={loading} pagination={{ pageSize: 20 }}
        locale={{ emptyText: <Empty description="暂无日志" /> }} />
    </>
  )
}

function SystemSettings() {
  const [config, setConfig] = useState<any>({})
  const [loading, setLoading] = useState(false)

  const fetchConfig = async () => {
    setLoading(true)
    try {
      const res: any = await getSystemConfig()
      setConfig(res.data || {})
    } catch { /* handled */ }
    finally { setLoading(false) }
  }

  useEffect(() => { fetchConfig() }, [])

  const handleSave = async () => {
    await updateSystemConfig(config)
    message.success('配置已保存')
    fetchConfig()
  }

  return (
    <div style={{ maxWidth: 600 }}>
      <Form layout="vertical">
        <Form.Item label="上传大小限制 (MB)">
          <InputNumber value={config.max_upload_size_mb} onChange={(v) => setConfig({ ...config, max_upload_size_mb: v })} style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item label="允许的文件扩展名（逗号分隔）">
          <Input value={config.allowed_extensions} onChange={(e) => setConfig({ ...config, allowed_extensions: e.target.value })} />
        </Form.Item>
        <Form.Item label="开放注册">
          <Switch checked={config.allow_registration} onChange={(v) => setConfig({ ...config, allow_registration: v })} />
        </Form.Item>
        <Space>
          <Button type="primary" onClick={handleSave} loading={loading}>保存配置</Button>
          <Button icon={<DownloadOutlined />} href="/api/v1/admin/database/backup" target="_blank">下载数据库备份</Button>
        </Space>
      </Form>
    </div>
  )
}

function Dashboard() {
  const [stats, setStats] = useState<any>({})
  useEffect(() => {
    import('../api/admin').then(api => {
      api.getSystemConfig().then((res: any) => {})  // trigger auth
    })
    const token = localStorage.getItem('token')
    fetch('/api/v1/admin/dashboard', { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.json()).then(r => setStats(r.data || {})).catch(() => {})
  }, [])

  return (
    <div>
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col span={6}><Card><Statistic title="总用户" value={stats.total_users || 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="活跃用户" value={stats.active_users || 0} suffix={`/ ${stats.total_users || 0}`} /></Card></Col>
        <Col span={6}><Card><Statistic title="文件总数" value={stats.total_files || 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="分享总数" value={stats.total_shares || 0} /></Card></Col>
      </Row>
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col span={6}><Card><Statistic title="总存储用量" value={stats.storage_used_display || '0 B'} /></Card></Col>
        <Col span={6}><Card><Statistic title="禁用用户" value={stats.disabled_users || 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="近7天新增" value={stats.new_users_last_7_days || 0} /></Card></Col>
      </Row>
      <Card title="文件类型分布" size="small" style={{ marginBottom: 16 }}>
        {(stats.file_type_stats || []).map((item: any) => (
          <div key={item.category} style={{ marginBottom: 8 }}>
            <Tag>{item.category}</Tag>
            <Progress percent={Math.round(item.size / (stats.storage_used_bytes || 1) * 100)} size="small" format={() => item.display} />
          </div>
        ))}
      </Card>
      <Card title="存储用量 Top 10" size="small">
        <Table
          rowKey="id"
          dataSource={stats.top_storage_users || []}
          columns={[
            { title: '用户', dataIndex: 'username' },
            { title: '已用', render: (_: any, r: any) => r.storage_used > 1073741824 ? `${(r.storage_used / 1073741824).toFixed(2)} GB` : `${(r.storage_used / 1048576).toFixed(1)} MB` },
            { title: '配额', render: (_: any, r: any) => r.storage_quota === 0 ? '不限' : `${(r.storage_quota / 1073741824).toFixed(1)} GB` },
            { title: '使用率', render: (_: any, r: any) => r.storage_quota === 0 ? '-' : `${((r.storage_used / r.storage_quota) * 100).toFixed(1)}%` },
          ]}
          pagination={false}
          size="small"
        />
      </Card>
    </div>
  )
}

export default function AdminPage() {
  return (
    <Tabs
      items={[
        { key: 'dashboard', label: <span><DashboardOutlined /> 仪表盘</span>, children: <Dashboard /> },
        { key: 'users', label: <span><UserAddOutlined /> 用户管理</span>, children: <UserManagement /> },
        { key: 'logs', label: <span><FileTextOutlined /> 操作日志</span>, children: <SystemLogs /> },
        { key: 'settings', label: <span><SettingOutlined /> 系统配置</span>, children: <SystemSettings /> },
      ]}
    />
  )
}
