import { useState, useEffect } from 'react'
import { Timeline, Typography, Spin } from 'antd'
import {
  UploadOutlined, FolderAddOutlined, EditOutlined, DeleteOutlined,
  UndoOutlined, CopyOutlined, DownloadOutlined, ShareAltOutlined,
} from '@ant-design/icons'
import client from '../api/client'
import dayjs from 'dayjs'

const { Text } = Typography

const ICON_MAP: Record<string, React.ReactNode> = {
  upload: <UploadOutlined style={{ color: '#1677ff' }} />,
  mkdir: <FolderAddOutlined style={{ color: '#faad14' }} />,
  rename: <EditOutlined style={{ color: '#722ed1' }} />,
  move: <CopyOutlined style={{ color: '#13c2c2' }} />,
  copy: <CopyOutlined style={{ color: '#13c2c2' }} />,
  delete: <DeleteOutlined style={{ color: '#ff4d4f' }} />,
  restore: <UndoOutlined style={{ color: '#52c41a' }} />,
  download: <DownloadOutlined style={{ color: '#1677ff' }} />,
  share_create: <ShareAltOutlined style={{ color: '#eb2f96' }} />,
  empty_trash: <DeleteOutlined style={{ color: '#ff4d4f' }} />,
}

const LABEL_MAP: Record<string, string> = {
  upload: '上传', mkdir: '新建文件夹', rename: '重命名', move: '移动',
  copy: '复制', delete: '删除', restore: '恢复', permanent_delete: '永久删除',
  download: '下载', share_create: '分享', share_delete: '取消分享', empty_trash: '清空回收站',
}

export default function RecentActivity({ refreshKey }: { refreshKey?: number }) {
  const [items, setItems] = useState<any[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    client.get('/files/activity', { params: { limit: 8 } })
      .then((res: any) => setItems(res.data || []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [refreshKey])

  if (loading) return <Spin size="small" style={{ padding: 16 }} />
  if (items.length === 0) return <Text type="secondary" style={{ padding: 16, display: 'block', fontSize: 12 }}>暂无操作记录</Text>

  return (
    <div style={{ padding: '8px 16px' }}>
      <Text type="secondary" style={{ fontSize: 11, fontWeight: 'bold', textTransform: 'uppercase' }}>最近操作</Text>
      <Timeline
        items={items.map((item: any) => ({
          dot: ICON_MAP[item.action] || undefined,
          children: (
            <div>
              <Text style={{ fontSize: 12 }}>{LABEL_MAP[item.action] || item.action}</Text>
              <br />
              <Text type="secondary" style={{ fontSize: 10 }}>{dayjs(item.created_at).format('MM-DD HH:mm')}</Text>
            </div>
          ),
        }))}
        style={{ marginTop: 8 }}
      />
    </div>
  )
}
