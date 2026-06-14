import { useState, useEffect } from 'react'
import { Table, Button, Space, Modal, message, Tag, Input, Empty } from 'antd'
import { DeleteOutlined, CopyOutlined, LinkOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { getMyShares, deleteShare } from '../api/shares'
import dayjs from 'dayjs'

interface ShareItem {
  id: number
  file_id: number
  code: string
  password: string
  expire_at: string | null
  view_count: number
  created_at: string
}

export default function SharePage() {
  const [shares, setShares] = useState<ShareItem[]>([])
  const [loading, setLoading] = useState(false)

  const fetchShares = async () => {
    setLoading(true)
    try {
      const res: any = await getMyShares()
      setShares(res.data?.items || res.data || [])
    } catch {
      // handled
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchShares() }, [])

  const handleDelete = (id: number) => {
    Modal.confirm({
      title: '取消分享',
      content: '该分享链接将失效',
      onOk: async () => {
        await deleteShare(id)
        message.success('已取消分享')
        fetchShares()
      },
    })
  }

  const copyLink = (code: string) => {
    const url = `${window.location.origin}/s/${code}`
    navigator.clipboard.writeText(url).then(() => message.success('链接已复制'))
  }

  const columns: ColumnsType<ShareItem> = [
    { title: '分享码', dataIndex: 'code', key: 'code', render: (c: string) => <Tag color="blue">{c}</Tag> },
    { title: '提取码', dataIndex: 'password', key: 'password', render: (p: string) => p ? <Tag>{p}</Tag> : <Tag color="green">无</Tag>, width: 100 },
    { title: '过期时间', dataIndex: 'expire_at', key: 'expire', width: 180,
      render: (t: string) => {
        if (!t) return <Tag color="green">永不过期</Tag>
        const exp = dayjs(t)
        const now = dayjs()
        if (exp.isBefore(now)) return <Tag color="red">已过期</Tag>
        if (exp.diff(now, 'hour') < 24) return <Tag color="orange">即将过期 ({exp.format('MM-DD HH:mm')})</Tag>
        return <Tag color="blue">{exp.format('YYYY-MM-DD HH:mm')}</Tag>
      },
    },
    { title: '访问次数', dataIndex: 'view_count', key: 'views', width: 100 },
    { title: '创建时间', dataIndex: 'created_at', key: 'created', render: (t: string) => dayjs(t).format('YYYY-MM-DD HH:mm'), width: 180 },
    {
      title: '操作', key: 'action', width: 200,
      render: (_, record) => (
        <Space>
          <Button size="small" icon={<CopyOutlined />} onClick={() => copyLink(record.code)}>复制链接</Button>
          <Button size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(record.id)}>取消分享</Button>
        </Space>
      ),
    },
  ]

  return (
    <Table rowKey="id" columns={columns} dataSource={shares} loading={loading}
      pagination={{ pageSize: 20 }}
      locale={{ emptyText: <Empty description="暂无分享记录" /> }}
    />
  )
}
