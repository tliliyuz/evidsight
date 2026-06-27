/**
 * FailedView 组件测试
 *
 * - recoverable 分支显示禁用 retry 按钮
 * - recoverable=false 显示提示文案
 * - 点击返回 emit back
 * - 错误消息解析（JSON / 多行 / 普通字符串）
 * - 标准错误码展示与异常类名下沉
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import FailedView from '@/components/report/FailedView.vue'

function mountFailed(props = {}) {
  return mount(FailedView, {
    props: {
      errorCode: 'E3104',
      errorMessage: 'Synthesis 失败',
      failedPhase: 'synthesis',
      recoverable: true,
      ...props,
    },
    global: { plugins: [createPinia()] },
  })
}

describe('FailedView', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('recoverable=true 显示禁用态断点续跑按钮', () => {
    const wrapper = mountFailed()
    const btn = wrapper.find('.retry-btn')
    expect(btn.exists()).toBe(true)
    expect(btn.attributes('disabled')).toBeDefined()
    expect(btn.text()).toContain('断点续跑')
  })

  it('recoverable=false 显示不可恢复提示', () => {
    const wrapper = mountFailed({ recoverable: false })
    expect(wrapper.find('.retry-btn').exists()).toBe(false)
    expect(wrapper.text()).toContain('无法恢复')
  })

  it('显示标准错误码与失败阶段', () => {
    const wrapper = mountFailed()
    const codeBadge = wrapper.find('.failed-error-code')
    expect(codeBadge.exists()).toBe(true)
    expect(codeBadge.text()).toBe('E3104')
    expect(wrapper.text()).toContain('Synthesis')
  })

  it('非标准 errorCode（异常类名）下沉到详细原因，不占据错误码 badge', () => {
    const wrapper = mountFailed({
      errorCode: 'LLMAuthFailedException',
      errorMessage: 'LLM 认证失败',
    })
    const codeBadge = wrapper.find('.failed-error-code')
    expect(codeBadge.exists()).toBe(false)
    expect(wrapper.find('.failed-message').text()).toBe('LLM 认证失败')
    expect(wrapper.find('.failed-detail').text()).toContain('LLMAuthFailedException')
  })

  it('点击返回 emit back', async () => {
    const wrapper = mountFailed()
    await wrapper.find('.back-btn').trigger('click')
    expect(wrapper.emitted('back')).toHaveLength(1)
  })

  it('解析 Python dict 字符串并显示 message', () => {
    const wrapper = mountFailed({
      errorMessage: "500: {'code': 'E3111', 'message': 'LLM 调用返回未预期错误', 'detail': {'error_type': 'LLMUnknown', 'error_description': 'Connection error.', 'recoverable': true, 'retry_after_ms': 3000}}",
    })
    expect(wrapper.find('.failed-message').text()).toBe('LLM 调用返回未预期错误')
  })

  it('解析标准 JSON 字符串并显示 message', () => {
    const wrapper = mountFailed({
      errorMessage: JSON.stringify({ code: 'E3104', message: 'Synthesis 失败', detail: {} }),
    })
    expect(wrapper.find('.failed-message').text()).toBe('Synthesis 失败')
  })

  it('普通字符串错误消息原样显示', () => {
    const wrapper = mountFailed({ errorMessage: '网络连接已断开' })
    expect(wrapper.find('.failed-message').text()).toBe('网络连接已断开')
  })

  it('解析嵌套单引号 JSON 并显示最外层 message', () => {
    const wrapper = mountFailed({
      errorMessage: "{'code': 'E3110', 'message': 'LLM 认证失败', 'detail': {'error_type': 'LLMAuthFailed', 'error_description': \"Error code: 401 - {'error': {'message': 'Authentication Fails, Your api key: ****ea5a is invalid', 'type': 'authentication_error', 'param': None, 'code': 'invalid_request_error'}}\", 'recoverable': False}}",
    })
    expect(wrapper.find('.failed-message').text()).toBe('LLM 认证失败')
  })

  it('多行错误消息拆分为主消息与详细原因', () => {
    const wrapper = mountFailed({
      errorCode: 'E3110',
      errorMessage: 'LLM 认证失败\n\nLLMAuthFailedException: invalid api key',
    })
    expect(wrapper.find('.failed-message').text()).toBe('LLM 认证失败')
    expect(wrapper.find('.failed-detail').exists()).toBe(true)
    expect(wrapper.find('.detail-text').text()).toContain('LLMAuthFailedException')
  })

  it('标准错误码也可从错误消息中解析', () => {
    const wrapper = mountFailed({
      errorCode: 'LLMAuthFailedException',
      errorMessage: "500: {'code': 'E3110', 'message': 'LLM 认证失败'}",
    })
    const codeBadge = wrapper.find('.failed-error-code')
    expect(codeBadge.exists()).toBe(true)
    expect(codeBadge.text()).toBe('E3110')
  })
})
