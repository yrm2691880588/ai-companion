import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { queries } from "../lib/queries";
import { Link } from "react-router-dom";
import { ChevronRight, Download, Info, Settings, ShieldCheck } from "lucide-react";
import AppearanceCard from "../components/AppearanceCard";
import Modal from "../components/Modal";
import PageHeader from "../components/PageHeader";
import UserProfileForm from "../components/UserProfileForm";

/**
 * 我的：只放和你本人有关、别人不会关心的东西。
 *
 * 结构分两层，不再是一摞同权卡片：
 * 1. 上面 = 需要你填/选的东西（我的身份、外观）—— 每天可能改的；
 * 2. 下面 = 一行入口（系统设置、导出数据、关于）—— 偶尔点进去的。
 *
 * 之前五张卡片样式、内边距完全一样，眼睛没有落点，页面看着像复制粘贴。
 * 分层之后「改身份」和「去哪儿」一眼分得开。
 *
 * 设置已从一级导航移除，入口在这一行里。
 */
export default function MePage() {
  const infoQuery = useQuery(queries.systemInfo());
  const info = infoQuery.data;
  // 「关于」只有几行版本信息，不值得单开一个页面，用弹窗就够
  const [aboutOpen, setAboutOpen] = useState(false);

  return (
    <div>
      <PageHeader
        title="我的"
        description="你的身份与外观都在这台机器上，不需要登录。"
      />

      <div className="me-top" style={{ marginTop: 24 }}>
        <UserProfileForm
          title="我的身份"
          description="她默认会知道这些信息：怎么称呼你、你做什么、多大、在哪。不同伴侣可以单独覆盖。"
        />
        <AppearanceCard />
      </div>

      {/* 一行三个入口：原来它们各占一张大卡片，五张同权卡片堆下来最显乱 */}
      <nav className="entry-row" aria-label="设置与信息">
        <Link className="entry-item" to="/settings">
          <span className="entry-item-icon" aria-hidden="true">
            <Settings size={17} />
          </span>
          <span className="entry-item-text">
            <strong>系统设置</strong>
            <span>模型、语音、供应商</span>
          </span>
          <ChevronRight size={16} aria-hidden="true" />
        </Link>

        <a className="entry-item" href="/v1/me/export" target="_blank" rel="noreferrer">
          <span className="entry-item-icon" aria-hidden="true">
            <Download size={17} />
          </span>
          <span className="entry-item-text">
            <strong>导出数据</strong>
            <span>换设备时带走</span>
          </span>
          <ChevronRight size={16} aria-hidden="true" />
        </a>

        <button className="entry-item" onClick={() => setAboutOpen(true)}>
          <span className="entry-item-icon" aria-hidden="true">
            <Info size={17} />
          </span>
          <span className="entry-item-text">
            <strong>关于</strong>
            <span>v{info?.version ?? "…"} · 本地开源版</span>
          </span>
          <ChevronRight size={16} aria-hidden="true" />
        </button>
      </nav>

      {/* 隐私与安全说明：原来塞在「关于」卡片里和版本号混在一起，容易被忽略 */}
      <div className="me-note">
        <ShieldCheck size={15} aria-hidden="true" />
        <span>
          数据只存在本机。遇到危机时，请拨打全国心理援助热线 12356，紧急情况拨打 120。
        </span>
      </div>

      {aboutOpen && (
        <Modal open onClose={() => setAboutOpen(false)} title="关于">
          <p className="muted">AI 伴侣系统 v{info?.version ?? "…"} · 本地开源版。</p>
          {info && (
            <p className="muted">
              数据库迁移 {info.migration_head}
              {info.local_mode ? " · 本地单用户模式" : ""}
            </p>
          )}
          <p className="muted">
            所有伴侣、会话与记忆都只存在这台机器上，不会上传到任何服务器。
          </p>
        </Modal>
      )}
    </div>
  );
}
