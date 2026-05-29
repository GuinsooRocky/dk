/**
 * WeChat Bot - 监听个人微信消息，转发给 Claude Bridge
 * =====================================================
 *
 * 启动：
 *   npm install
 *   node wechat_bot.js
 *
 * 第一次运行会在终端显示二维码，用手机微信扫码登录。
 * 登录后机器人会在你账号下监听消息。
 *
 * 触发方式：
 *   - 私聊：发送以 "/c " 开头的消息   (例：/c 帮我看下天气)
 *   - 群聊：@机器人 + 内容
 *   - 给"文件传输助手"发任意消息（debug 用）
 */

import { WechatyBuilder, ScanStatus, log } from 'wechaty';
import qrcodeTerminal from 'qrcode-terminal';
import axios from 'axios';
import 'dotenv/config';

// ============ 配置 ============
const BRIDGE_URL = process.env.BRIDGE_URL || 'http://127.0.0.1:5858/chat';
const TRIGGER_PREFIX = process.env.TRIGGER_PREFIX || '/c ';
const BOT_NAME = process.env.BOT_NAME || 'claude-bot';
// 群里是否需要 @机器人 才回复（true 推荐，避免刷屏）
const GROUP_REQUIRE_MENTION = (process.env.GROUP_REQUIRE_MENTION || 'true') === 'true';

// ============ 创建 Bot ============
const bot = WechatyBuilder.build({
  name: BOT_NAME,
  puppet: 'wechaty-puppet-wechat4u',  // 免费 puppet，基于 web 微信协议
});

// ============ 事件处理 ============
bot.on('scan', (qrcode, status) => {
  if (status === ScanStatus.Waiting || status === ScanStatus.Timeout) {
    qrcodeTerminal.generate(qrcode, { small: true });
    console.log(`\n[扫码登录] 状态=${ScanStatus[status]}`);
    console.log(`如果终端二维码看不清，可在浏览器打开：`);
    console.log(`https://wechaty.js.org/qrcode/${encodeURIComponent(qrcode)}\n`);
  } else {
    console.log(`[扫码状态] ${ScanStatus[status]}`);
  }
});

bot.on('login', user => {
  console.log(`\n登录成功：${user.name()}`);
  console.log(`触发方式：私聊以 "${TRIGGER_PREFIX}" 开头，或群里 @${user.name()}\n`);
});

bot.on('logout', user => {
  console.log(`已登出：${user.name()}`);
});

bot.on('error', err => {
  console.error('Bot 错误：', err.message);
});

bot.on('message', async msg => {
  try {
    // 忽略自己发的消息
    if (msg.self()) return;
    // 只处理文本
    if (msg.type() !== bot.Message.Type.Text) return;

    const room = msg.room();
    const talker = msg.talker();
    const talkerName = talker.name();
    let text = msg.text();

    let shouldReply = false;
    let cleanText = text;

    if (room) {
      // 群聊：检查是否被 @
      if (GROUP_REQUIRE_MENTION) {
        const mentioned = await msg.mentionSelf();
        if (!mentioned) return;
        // 去掉 @机器人 的部分
        cleanText = text.replace(/@[^\s]+\s*/g, '').trim();
        shouldReply = true;
      } else {
        shouldReply = true;
      }
    } else {
      // 私聊：检查前缀
      // 文件传输助手特殊处理：任意消息都触发
      if (talkerName === '文件传输助手') {
        shouldReply = true;
      } else if (text.startsWith(TRIGGER_PREFIX)) {
        cleanText = text.slice(TRIGGER_PREFIX.length).trim();
        shouldReply = true;
      }
    }

    if (!shouldReply || !cleanText) return;

    const where = room ? `[群:${await room.topic()}]` : '[私聊]';
    console.log(`${where} ${talkerName}: ${cleanText}`);

    // 立即回复"思考中"以告知用户已收到
    if (room) {
      await room.say(`正在思考...`, talker);
    } else {
      await msg.say('正在思考...');
    }

    // 调用 Claude Bridge
    const startTime = Date.now();
    let reply;
    try {
      const resp = await axios.post(BRIDGE_URL, {
        user: talkerName,
        message: cleanText,
      }, { timeout: 600_000 });  // 10 分钟超时

      reply = resp.data?.text || '(空响应)';
      const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
      console.log(`  → 回复 (${elapsed}s, ${reply.length} 字)`);
    } catch (err) {
      reply = `Bridge 出错：${err.message}`;
      console.error('  → 调用 Bridge 失败：', err.message);
    }

    // 微信单条消息有长度限制，太长就分段
    const MAX_LEN = 1500;
    if (reply.length <= MAX_LEN) {
      if (room) {
        await room.say(reply, talker);
      } else {
        await msg.say(reply);
      }
    } else {
      const chunks = [];
      for (let i = 0; i < reply.length; i += MAX_LEN) {
        chunks.push(reply.slice(i, i + MAX_LEN));
      }
      for (let i = 0; i < chunks.length; i++) {
        const part = `[${i + 1}/${chunks.length}] ${chunks[i]}`;
        if (room) {
          await room.say(part, talker);
        } else {
          await msg.say(part);
        }
        // 防止发太快
        await new Promise(r => setTimeout(r, 800));
      }
    }
  } catch (err) {
    console.error('处理消息出错：', err);
  }
});

// ============ 启动 ============
console.log('启动 WeChat Bot...');
console.log(`  Bridge URL: ${BRIDGE_URL}`);
console.log(`  触发前缀（私聊）: "${TRIGGER_PREFIX}"`);
console.log(`  群里需要 @机器人: ${GROUP_REQUIRE_MENTION}`);
bot.start()
  .then(() => console.log('Bot 已启动，等待扫码...'))
  .catch(err => {
    console.error('启动失败：', err);
    process.exit(1);
  });
