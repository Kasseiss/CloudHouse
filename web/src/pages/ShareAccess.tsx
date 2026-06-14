import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { Card, Button, Input, Typography, Space, message, Descriptions, Result, List } from 'antd'
import { DownloadOutlined, LockOutlined, FileOutlined, FolderOutlined } from '@ant-design/icons'
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

  const { file, share, children } = shareData

  const childDownloadUrl = (childId: number) => {
    const pwd = share?.password || ''
    return `/api/v1/shares/${code}/download?password=${encodeURIComponent(pwd)}&child_id=${childId}`
  }

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: '#f0f2f5', padding: 24 }}>
      <Card style={{ width: file?.is_dir ? 600 : 500 }}>
        <Title level={4}>{file?.is_dir ? '📁' : '📄'} {file?.is_dir ? '分享文件夹' : '分享文件'}</Title>
        <Descriptions column={1} bordered size="small">
          <Descriptions.Item label="名称">{file?.name || '-'}</Descriptions.Item>
          <Descriptions.Item label={file?.is_dir ? '文件夹' : '文件大小'}>
            {file?.is_dir ? `${children?.length || 0} 个项目` : file?.file_size ? `${(file.file_size / 1024 / 1024).toFixed(2)} MB` : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="分享时间">{dayjs(share?.created_at).format('YYYY-MM-DD HH:mm')}</Descriptions.Item>
          <Descriptions.Item label="有效期">{share?.expire_at ? dayjs(share.expire_at).format('YYYY-MM-DD HH:mm') : '永久有效'}</Descriptions.Item>
        </Descriptions>

        {file?.is_dir && children && children.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <Title level={5}>文件夹内容</Title>
            <List
              size="small"
              dataSource={children}
              renderItem={(item: any) => (
                <List.Item
                  actions={[
                    !item.is_dir && (
                      <a key="dl" href={childDownloadUrl(item.id)} target="_blank">
                        <Button size="small" icon={<DownloadOutlined />}>下载</Button>
                      </a>
                    ),
                  ]}
                >
                  <Space>
                    {item.is_dir ? <FolderOutlined style={{ color: '#faad14' }} /> : <FileOutlined />}
                    <span>{item.name}</span>
                    {!item.is_dir && <span style={{ color: '#999', fontSize: 12 }}>{item.file_size > 1024 ? `${(item.file_size / 1024).toFixed(1)} KB` : `${item.file_size} B`}</span>}
                  </Space>
                </List.Item>
              )}
            />
          </div>
        )}

        {!file?.is_dir && (
          <div style={{ marginTop: 24, textAlign: 'center' }}>
            <Button type="primary" size="large" icon={<DownloadOutlined />} onClick={handleDownload} block>
              下载文件
            </Button>
          </div>
        )}
      </Card>
    </div>
  )
}
