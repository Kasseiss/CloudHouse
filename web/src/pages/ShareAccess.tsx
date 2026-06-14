import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { Card, Button, Input, Typography, Space, message, Descriptions, Result } from 'antd'
import { DownloadOutlined, LockOutlined } from '@ant-design/icons'
import { getShareInfo } from '../api/shares'
import dayjs from 'dayjs'

const { Title } = Typography

export default function ShareAccessPage() {
  const { code } = useParams<{ code: string }>()
  const [shareData, setShareData] = useState<any>(null)
  const [password, setPassword] = useState('')
  const [needPassword, setNeedPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const fetchShare = async (pwd = '') => {
    if (!code) return
    setLoading(true)
    setError('')
    try {
      const res: any = await getShareInfo(code, pwd)
      setShareData(res.data)
      setNeedPassword(false)
    } catch (err: any) {
      if (err?.response?.status === 403) {
        setNeedPassword(true)
      } else {
        setError(err?.response?.data?.message || '分享不存在或已过期')
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchShare()
  }, [code])

  const handleDownload = () => {
    if (!shareData?.file || !shareData?.share) return
    // Use public share download endpoint
    const pwd = shareData.share.password || ''
    window.open(`/api/v1/shares/${code}/download?password=${encodeURIComponent(pwd)}`, '_blank')
  }

  if (error) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh' }}>
        <Result status="error" title="无法访问" subTitle={error} />
      </div>
    )
  }

  if (needPassword) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: '#f0f2f5' }}>
        <Card style={{ width: 400 }}>
          <Title level={4}><LockOutlined /> 需要提取码</Title>
          <Space direction="vertical" style={{ width: '100%' }}>
            <Input.Password placeholder="请输入提取码" value={password} onChange={(e) => setPassword(e.target.value)} />
            <Button type="primary" block loading={loading} onClick={() => fetchShare(password)}>验证</Button>
          </Space>
        </Card>
      </div>
    )
  }

  if (!shareData) return null

  const { file, share } = shareData

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: '#f0f2f5' }}>
      <Card style={{ width: 500 }}>
        <Title level={4}>📁 分享文件</Title>
        <Descriptions column={1} bordered size="small">
          <Descriptions.Item label="文件名">{file?.name || '-'}</Descriptions.Item>
          <Descriptions.Item label="文件大小">{file?.file_size ? `${(file.file_size / 1024 / 1024).toFixed(2)} MB` : '-'}</Descriptions.Item>
          <Descriptions.Item label="分享时间">{dayjs(share?.created_at).format('YYYY-MM-DD HH:mm')}</Descriptions.Item>
          <Descriptions.Item label="有效期">{share?.expire_at ? dayjs(share.expire_at).format('YYYY-MM-DD HH:mm') : '永久有效'}</Descriptions.Item>
        </Descriptions>
        <div style={{ marginTop: 24, textAlign: 'center' }}>
          <Button type="primary" size="large" icon={<DownloadOutlined />} onClick={handleDownload} block>
            下载文件
          </Button>
        </div>
      </Card>
    </div>
  )
}
