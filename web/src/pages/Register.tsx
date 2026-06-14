import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Form, Input, Button, Card, Typography, message, Progress } from 'antd'
import { UserOutlined, LockOutlined, MailOutlined } from '@ant-design/icons'
import { register } from '../api/auth'

const { Title } = Typography

function getStrength(pwd: string): { percent: number; color: string; text: string } {
  const len = pwd.length
  const hasUpper = /[A-Z]/.test(pwd)
  const hasLower = /[a-z]/.test(pwd)
  const hasNum = /\d/.test(pwd)
  const hasSym = /[^A-Za-z0-9]/.test(pwd)
  const variety = [hasUpper, hasLower, hasNum, hasSym].filter(Boolean).length

  if (len < 6) return { percent: 20, color: '#ff4d4f', text: '太短' }
  if (len >= 6 && variety <= 1) return { percent: 35, color: '#ff4d4f', text: '弱' }
  if (len >= 8 && variety >= 2) return { percent: 60, color: '#faad14', text: '中等' }
  if (len >= 10 && variety >= 3) return { percent: 85, color: '#1677ff', text: '强' }
  if (len >= 12 && variety >= 4) return { percent: 100, color: '#52c41a', text: '很强' }
  return { percent: 50, color: '#faad14', text: '中等' }
}

export default function RegisterPage() {
  const [loading, setLoading] = useState(false)
  const [pwdStrength, setPwdStrength] = useState({ percent: 0, color: '#ff4d4f', text: '' })
  const navigate = useNavigate()

  const onFinish = async (values: { username: string; password: string; email: string }) => {
    setLoading(true)
    try {
      await register(values.username, values.password, values.email)
      message.success('注册成功，请登录')
      navigate('/login')
    } catch {
      // error handled by interceptor
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' }}>
      <Card style={{ width: 400, boxShadow: '0 4px 24px rgba(0,0,0,0.15)' }}>
        <Title level={3} style={{ textAlign: 'center', marginBottom: 32 }}>☁ 注册 CloudDisk</Title>
        <Form onFinish={onFinish} size="large">
          <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }, { min: 3, message: '至少3个字符' }]}>
            <Input prefix={<UserOutlined />} placeholder="用户名" />
          </Form.Item>
          <Form.Item name="email" rules={[{ type: 'email', message: '请输入有效的邮箱' }]}>
            <Input prefix={<MailOutlined />} placeholder="邮箱（选填）" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }, { min: 6, message: '至少6位' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="密码"
              onChange={(e) => setPwdStrength(getStrength(e.target.value))} />
            {pwdStrength.text && (
              <Progress percent={pwdStrength.percent} strokeColor={pwdStrength.color}
                size="small" format={() => pwdStrength.text} style={{ marginTop: 4 }} />
            )}
          </Form.Item>
          <Form.Item name="confirm" dependencies={['password']} rules={[{ required: true }, ({ getFieldValue }) => ({
            validator(_, value) {
              if (!value || getFieldValue('password') === value) return Promise.resolve()
              return Promise.reject(new Error('两次输入的密码不一致'))
            },
          })]}>
            <Input.Password prefix={<LockOutlined />} placeholder="确认密码" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block>注册</Button>
          </Form.Item>
          <div style={{ textAlign: 'center' }}>
            <Link to="/login">已有账号？去登录</Link>
          </div>
        </Form>
      </Card>
    </div>
  )
}
