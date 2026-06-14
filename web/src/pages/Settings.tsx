import { useState, useEffect } from 'react'
import { Card, Descriptions, Button, Input, Space, message, Statistic, Row, Col, Progress } from 'antd'
import { KeyOutlined, SaveOutlined } from '@ant-design/icons'
import { useAuth } from '../store/auth'
import { changePassword } from '../api/auth'
import client from '../api/client'

const formatBytes = (bytes: number) => {
  if (bytes === 0) return '不限制'
  if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB'
  return (bytes / 1073741824).toFixed(2) + ' GB'
}

export default function SettingsPage() {
  const { user, refreshUser } = useAuth()
  const [oldPwd, setOldPwd] = useState('')
  const [newPwd, setNewPwd] = useState('')
  const [saving, setSaving] = useState(false)
  const [storage, setStorage] = useState<any>(null)

  useEffect(() => {
    client.get('/files/storage').then((res: any) => setStorage(res.data)).catch(() => {})
  }, [])

  const handlePasswordChange = async () => {
    if (!newPwd || newPwd.length < 6) {
      message.error('新密码至少6位')
      return
    }
    setSaving(true)
    try {
      await changePassword(oldPwd, newPwd)
      message.success('密码修改成功')
      setOldPwd('')
      setNewPwd('')
    } catch {
      // handled
    } finally {
      setSaving(false)
    }
  }

  const usagePercent = storage
    ? (storage.storage_quota > 0 ? ((storage.storage_used / storage.storage_quota) * 100).toFixed(1) : 0)
    : 0

  return (
    <div style={{ maxWidth: 700 }}>
      <h3 style={{ marginBottom: 16 }}>个人设置</h3>

      <Card title="账号信息" style={{ marginBottom: 16 }}>
        <Descriptions column={1} size="small">
          <Descriptions.Item label="用户名">{user?.username}</Descriptions.Item>
          <Descriptions.Item label="邮箱">{user?.email || '-'}</Descriptions.Item>
          <Descriptions.Item label="角色">{user?.role === 'admin' ? '管理员' : '普通用户'}</Descriptions.Item>
          <Descriptions.Item label="注册时间">{user?.created_at ? new Date(user.created_at).toLocaleDateString() : '-'}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="存储空间" style={{ marginBottom: 16 }}>
        <Row gutter={24}>
          <Col span={8}>
            <Statistic title="已用空间" value={formatBytes(storage?.storage_used || 0)} />
          </Col>
          <Col span={8}>
            <Statistic title="总配额" value={formatBytes(storage?.storage_quota || 0)} />
          </Col>
          <Col span={8}>
            <Statistic title="使用率" value={usagePercent} suffix="%" />
          </Col>
        </Row>
      </Card>

      <Card title="修改密码">
        <Space direction="vertical" style={{ width: '100%' }}>
          <Input.Password
            placeholder="原密码"
            value={oldPwd}
            onChange={(e) => setOldPwd(e.target.value)}
            prefix={<KeyOutlined />}
          />
          <Input.Password
            placeholder="新密码（至少6位）"
            value={newPwd}
            onChange={(e) => {
              setNewPwd(e.target.value)
              const v = e.target.value
              const hasUpper = /[A-Z]/.test(v); const hasLower = /[a-z]/.test(v)
              const hasNum = /\d/.test(v); const hasSym = /[^A-Za-z0-9]/.test(v)
              const variety = [hasUpper, hasLower, hasNum, hasSym].filter(Boolean).length
              const pct = v.length < 6 ? 20 : variety <= 1 ? 35 : variety >= 3 ? 85 : 60
              const el = document.getElementById('pwd-bar')
              if (el) (el as any).style.width = pct + '%'
            }}
            prefix={<KeyOutlined />}
          />
          {newPwd && (
            <Progress
              percent={newPwd.length < 6 ? 20 : /[A-Z]/.test(newPwd) && /[a-z]/.test(newPwd) && /\d/.test(newPwd) ? 85 :
                /[A-Za-z]/.test(newPwd) && /\d/.test(newPwd) ? 60 : 35}
              strokeColor={newPwd.length < 6 ? '#ff4d4f' : newPwd.length >= 8 ? '#52c41a' : '#faad14'}
              size="small" format={() => newPwd.length < 6 ? '太短' : newPwd.length >= 10 ? '强' : newPwd.length >= 8 ? '中等' : '弱'}
            />
          )}
          <Button type="primary" icon={<SaveOutlined />} onClick={handlePasswordChange} loading={saving}>
            保存密码
          </Button>
        </Space>
      </Card>
    </div>
  )
}
