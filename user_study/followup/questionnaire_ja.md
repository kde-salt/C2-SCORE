# フォローアップ・ユーザスタディ：スキーマのランキング評価

本調査は、以前実施したユーザスタディの補足実験です。今回は Neo4j 環境への接続は不要で、
本文書に掲載された図と表のみを見て、Google Form で回答していただきます。
所要時間の目安は 25〜30 分です。

## 目次
- [0. お願いと注意事項](#0-お願いと注意事項)
- [1. プロパティグラフとは](#1-プロパティグラフとは)
- [2. スキーマ（Schema）とは](#2-スキーマschemaとは)
- [3. タスクの説明](#3-タスクの説明)
- [タスク1（Q5-1）: 音楽](#タスク1q5-1-音楽)
- [タスク2（Q5-2）: 学術文献](#タスク2q5-2-学術文献)
- [タスク3（Q5-3）: EC（電子商取引）](#タスク3q5-3-ec電子商取引)
- [おわりに](#おわりに)
---

## 0. お願いと注意事項

回答を始める前に、次の4点をご確認ください。

- **⏱ 今回は所要時間の計測をお願いします。**
  **タスク1に取り掛かり始めたタイミングから計測を開始**し、**回答にかかった合計時間**を
  Google Form にご記入ください。
  ここまでの説明（プロパティグラフ・スキーマの説明、タスクの説明）を読んでいる時間は**含めません**。
  一方、タスクを開始したあとに説明を読み返した場合は、その時間は**含めてください**。
  3つのタスクを続けて解いた場合は**開始から終了までの時間**を、
  複数回に分けて取り組んだ場合は**各回の時間を合計した値**をご記入ください
  （厳密な計測は不要です。分単位の概算で構いません）。
- **参加者に配布した Google Form を、案内した期限までに送信してください。**
- **生成AI（ChatGPT などの LLM）を使用しないでください。**
  本文書のグラフデータやスキーマを生成AIに入力したり、順位付け・評価を生成AIに依頼したりしないでください。
- **3つのタスクすべてに回答してください。**
  未回答のタスクがある回答は**無効回答**となり、集計に使用できません。

---

## 1. プロパティグラフとは
私たちの身の回りの情報は、人と人のつながり、ユーザと投稿、商品と購入者など、**「もの同士の関係」** で成り立っています。
しかし、従来の リレーショナルデータベース（RDB） では、これらを「行と列の表（テーブル）」として扱うため、複雑な関係を表すには多くの表をつなぐ結合（`JOIN`）操作が必要になります。

たとえば、「Aさんをフォローしている人から“いいね”された投稿」を調べたいとします。この場合、

- 「ユーザ」テーブル
- 「フォロー関係」テーブル
- 「投稿」テーブル
- 「いいね」テーブル

といった複数の表を結合して検索する必要があります。
その結果、SQL文は複雑になり、パフォーマンスも低下しがちです。

こうした複雑な関係を自然に表現できるのが、グラフデータモデル です。グラフモデルでは、データを **ノード（頂点）** と **エッジ（辺）** で表し、「誰が」「どの投稿に」「どんな関係で」つながっているかを図として表現できます。
たとえば「Aさん ←(フォロー)- Bさん -(いいね)→ 投稿X」というように、関係性を直感的に捉えやすくなります。

その中でも特に柔軟で表現力が高いのが **プロパティグラフ（Property Graph）** です。
プロパティグラフでは、ノードとエッジの両方に **ラベル（大まかな種類を表す属性情報）** や **プロパティ（より詳細な属性情報）** を持たせることができます。たとえば、ノードが人であることを表す`Person`ラベルを付与したり、「いいね」を表すエッジに「いついいねしたか」を示す`timestamp`プロパティを追加したりできます。

図1にプロパティグラフの例を示します。このプロパティグラフは、ユーザ同士のフォロー関係や投稿の作成関係を表現しています。
このように、プロパティグラフは複雑な関係性を直感的に表現できるため、ソーシャルネットワーク分析、推薦システム、知識グラフなど、様々な分野で活用されています。以降では、図1を例に、プロパティグラフの各要素について説明します。

<figure>
  <div align="center">
    <img src="img/image-1.png" alt="プロパティグラフの例" width="500" />
    <p><strong>図1：プロパティグラフの例</strong></p>
  </div>
</figure>

### (1) ノード
図1の $n_1, n_2, \cdots , n_5$がノードに該当します。
ノードは、人、場所、モノ、概念など、様々な実体を表現するために使用されます。

### (2) エッジ
図1の $e_1, e_2, \cdots, e_7$がエッジに該当します。
エッジはノード間の関係性を示します。今回のプロパティグラフではエッジは方向を持ち、始点ノードから終点ノードへ向かう矢印で表現されます。

### (3) ラベル
図1の`Person`や`Student`がノードのラベル、`FOLLOWS`や`CREATES`がエッジのラベルに該当します。
ラベルはノードやエッジの大まかな属性を示すために使用されます。
1つのノードやエッジは、0個以上のラベルを持つことができます。

### (4) プロパティ
図1のノード $n_1$の`name: "Alice"`や`age: 18`、エッジ $e_4$の`ts: 01-12-10:00`などがプロパティに該当します。
また`name`や`age`をプロパティの **キー** 、`"Alice"`や`18`を **値**と呼びます。
プロパティはノードやエッジに付随する詳細な情報を格納するための属性です。
1つのノードやエッジは、0個以上のプロパティを持つことができます。


---

## 2. スキーマ（Schema）とは

プロパティグラフでは、データをノードとエッジで表現し、それぞれにラベルやプロパティを持たせられます。
しかし、<u>データの種類が増えていくと、「どんなノードやエッジが存在するのか」「それぞれにどんなラベルやプロパティを持たせるべきか」を整理しておかないと、データの構造がバラバラになってしまいます。</u>またその結果としてデータの整合性が失われたり、クエリのパフォーマンスが低下したりする恐れがあります。

そこで登場するのが **スキーマ（Schema）** です。スキーマは、グラフデータの設計図やルールブックのようなものです。スキーマを用いて、どんな種類のノードやエッジがあり、それぞれにどんな情報を持たせられるのかを、あらかじめ定義することで、データの一貫性と整合性を保つことができます。

例えばSNSの例を考えてみましょう。

- ユーザは（`Person`）というラベルを持つノードで表現し、そのノードには「名前（`name`）」「年齢（`age`）」などのプロパティがある
- 投稿は（`Post`）というラベルを持つノードで表現し、そのノードには「内容（`text`）」がある
- 「いいね（`LIKES`）」というエッジは「ユーザ」と「投稿」を結び、そのエッジには「いいねした日時（`timestamp`）」がある

このように、<u>スキーマを定義しておくことで「どの種類のノードがどの種類のノードとつながるのか」「どのプロパティが必須なのか」が明確になります。結果としてデータ構造の一貫性が保たれ、クエリの最適化やデータの検証が容易になります。</u>

さらに、スキーマには **「型の継承関係」** を定義することもできます。例えば、「ユーザ」型を基に「学生ユーザ」や「企業アカウント」といった型を派生させることで、スキーマで定義した共通部分を再利用しながらモデルを整理・拡張できます。これにより、複雑なデータモデルを簡潔に、かつ柔軟に表現できるようになります。

図2にスキーマの例を示します。このスキーマは、図1のプロパティグラフに対応しています。
スキーマはノード型とエッジ型で構成されており、ノード型とエッジ型にはそれぞれラベル制約、プロパティ制約、端点制約（エッジ型のみ）などの情報が含まれます。以降は図2のスキーマを例に、スキーマの各要素について説明します。


<table>
  <tr>
    <td align="center" valign="top">
      <img src="img/image-2.png" alt="スキーマの例" width="340" /><br />
      <strong>図2：スキーマの例</strong>
    </td>
    <td align="center" valign="top">
      <img src="img/image-1.png" alt="プロパティグラフの例" width="420" /><br />
      <strong>（再掲）図1：プロパティグラフの例</strong>
    </td>
  </tr>
</table>

### (1) ノード型

ノード型には以下の情報が含まれます：
- **ラベル制約**
  - 必須ラベル
  - 任意ラベル（今回のユーザスタディでは使用しないため以降は省略）
- **プロパティ制約**
  - 必須プロパティ
  - 任意プロパティ：図中ではプロパティ名の後に`?`を付与して表現

例えば、図2のノード型 $nt_1$は、以下のような制約を持ちます：
- 必須ラベル：`Person`が必ず存在する
- 必須プロパティ：`name`というプロパティが必ず存在する
- 任意プロパティ：`age`というプロパティが存在しても良い（`?`が付与されているため）

図1のノード $n_1$および $n_2$は図2のノード型 $nt_1$の制約に従っています。

### (2) エッジ型
エッジ型には以下の情報が含まれます：
- **ラベル制約**
  - 必須ラベル
  - 任意ラベル（今回のユーザスタディでは使用しないため以降は省略）
- **プロパティ制約**
  - 必須プロパティ
  - 任意プロパティ
- **端点制約**：エッジがどの種類のノード同士を結ぶかを定めるルールです。エッジはノード同士の関係を表しますが、どんなノードでも自由に結べるわけではありません。そこで「端点制約」により **始点ノード型** と **終点ノード型** を指定します。具体的には以下の2点を定義します：
  - 始点ノード型：どんなタイプのノードをエッジの始点にできるか
  - 終点ノード型：どんなタイプのノードをエッジの終点にできるか

例えば、図2のエッジ型 $et_2$は、以下のような制約を持ちます：
- 必須ラベル：`CREATES`が必ず存在する
- 必須プロパティ：`ts`
- 任意プロパティ：なし
- 端点制約：
  - 始点ノード型が $nt_1$
  - 終点ノード型が $nt_3$
図1のエッジ $e_4$はエッジ型 $et_2$の制約に従っています。


### (3) ノード型の継承
ノード型の **継承** は、あるノード型が別のノード型の属性や制約を引き継ぐことを指します。例えば `Person`というラベルを持つノード型を基礎にして、`Student`や`Teacher`という派生ノード型を作成することができます。

継承関係は、`EXTENDS`という特別なエッジを用いて表現されます。
ノード型の継承を用いることで、共通の属性や制約を再利用し、データモデルをより簡潔に表現できます。
ここで、`EXTENDS`エッジの始点ノード型を**子ノード型**、終点ノード型を**親ノード型**と呼びます。

ノード型の継承を行うと、以下のルールが適用されます：
- ルール1. 子ノード型は親ノード型のラベル制約とプロパティ制約をすべて引き継ぐ
- ルール2. 親ノード型を始点または終点に持つエッジ型の端点制約を、子ノード型にも拡張する

#### 具体例
ここで、小さな具体例を示します。
図3は、図2から一部のノード型とエッジ型、および継承関係を抜き出した部分グラフです。

<table>
  <tr>
    <td align="center" valign="top">
      <img src="img/image-3.png" alt="ノード型の継承の例" width="370" /><br />
      <strong>図3：図2のスキーマの部分グラフ</strong>
    </td>
    <td align="center" valign="top">
      <img src="img/image-4.png" alt="ノード型の継承の例（展開後）" width="355" /><br />
      <strong>図4：図3の継承関係を展開したスキーマ</strong>
    </td>
  </tr>
</table>

図3の子ノード型 $nt_2$は親ノード型 $nt_1$を継承しています。
したがって、ルール1に従い、子（ $nt_2$）は、親（ $nt_1$）が持つ以下の制約を引き継ぎます：
- 必須ラベル：`Person`が必ず存在する
- 必須プロパティ：`name`が必ず存在する
- 任意プロパティ：`age`が存在しても良い

さらに、ルール2に従い、図3の親（ $nt_1$）を始点とするエッジ型の端点制約が、子（ $nt_2$）にも拡張されます。例えばエッジ型 $et_2$の始点ノード型は $nt_1$ですが、その子である $nt_2$もこのエッジ型の始点ノード型として使用できるようになります。

継承関係を具体的なスキーマ構造に置き換える操作を **展開** と呼びます。図3の継承関係を展開すると図4のようになります。
`EXTENDS`エッジは不要になるため削除され、子ノード型が親ノード型の制約を引き継いだ形になります。
例えば、図4のノード型 $nt_5$には、元々保有していた`Student`という必須ラベルに加えて、継承元のノード型 $nt_1$のラベルやプロパティが追加されています。

図3のスキーマと図4のスキーマは全く同じ意味を持ちますが、図4の方が冗長になります。また図4のスキーマは継承関係を展開しているため、ノード型やエッジ型の追加・変更があった場合にメンテナンスが大変になります。
例えば、図4のスキーマでノード型 $nt_4$に新たな必須プロパティ `email`を追加した場合、ノード型 $nt_5$にも同じ必須プロパティを追加する必要があります。しかし、図2のスキーマであればノード型 $nt_1$に`email`を追加するだけで済みます。

このように、ノード型の継承を使用することで、スキーマをより簡潔に保ち、メンテナンス性を向上させることができます。

### (4) エッジ型の継承
今回のユーザスタディではエッジ型の継承は使用しないため省略します。

### (5) 補足
- スキーマには他にも「エッジカーディナリティ（1対1、1対多、多対多など）」や「ノードの一意性制約」などの概念がありますが、今回のユーザスタディでは使用しないため省略します。
- 参考に、図2のスキーマを展開した図を以下に示します。


<!-- 図2の再掲及び図5を横並びで表示 -->
<table>
  <tr>
    <td align="center" valign="top">
      <img src="img/image-2.png" alt="スキーマの例" width="380" /><br />
      <strong>（再掲）図2：スキーマの例</strong>
    </td>
    <td align="center" valign="top">
      <img src="img/image-5.png" alt="スキーマの例（展開後）" width="380" /><br />
      <strong>図5：図2の継承関係を展開したスキーマ</strong>
    </td>
  </tr>
</table>

---

## 3. タスクの説明

以降に **3つのタスク** があります。各タスクでは、
**1つのグラフデータ**（図＋ノード表・エッジ表）と **4つの候補スキーマ（A〜D）** を提示します。

データの各ノードには `Album #1` のような **ノード ID**（ラベル＋通し番号）を付けています。
図のボックス見出しと、ノード表・エッジ表の ID は同じものを指します。

- データは正しい内容を持っており、欠損や誤りはありません。
  **スキーマとデータが整合しない場合は、スキーマ側に誤りがあると考えてください。**
- 「このグラフデータを最も適切に表現しているスキーマ」から順に、
  **各タスクの4候補に 1位〜4位の順位** を付けてください。
  **同率順位は不可**です（1位、2位、2位、4位などは認められません）。
- 評価に「正解」はありません。**直感的に感じた適切さ**を率直にご回答ください。

評価の際は、例えば以下のような点が参考になります（これ以外の観点でも構いません）。

- ノード型・エッジ型のラベルやプロパティがデータと整合しているか
- 必須・任意（`?`）の区別がデータの実態と対応しているか
- エッジ型の端点（矢印の向き・接続先）が正しいか
- 誤りの**個数**が少ないほど、また誤りの**重大性**が低いほど高評価

### 所要時間の計測について

**計測は、下のタスク1に取り掛かり始めたタイミングから開始してください。**
ここまでの説明（§1 プロパティグラフ・§2 スキーマ・本節のタスクの説明）を読んでいる時間は**計測に含めません**。
一方、タスクを開始したあとにこれらの説明を読み返した場合は、その時間は**計測に含めてください**。
3つのタスクを続けて解いた場合は開始から終了までの時間を、複数回に分けて取り組んだ場合は各回の時間を合計した値を、
Google Form にご記入ください（分単位の概算で構いません）。

### 注意事項

- 本文書のグラフデータやスキーマを生成AIに入力したり、生成AIに評価を依頼したりしないでください。
- 回答は参加者に配布した Google Form で収集します。
  フォームでは各候補について「Q5-1-A のようなID ＝ 順位（1〜4）」の形式で回答します。

---

> [!IMPORTANT]
> **⏱ ここから先が問題です。時間の計測を開始してください。**
>
> タスク1に取り掛かる前に、タイマーを開始するか現在の時刻を控えてください。
> ここまでの説明（§1・§2・§3）を読んでいた時間は計測に含めません。
> 3つのタスクをすべて解き終えたら、かかった時間を Google Form にご記入ください
> （分単位の概算で構いません）。

## タスク1（Q5-1）: 音楽

### データ

<div align="center"><img src="img/q5-1-instance.png" width="820" /></div>

<details><summary><strong>ノード一覧（クリックで展開）</strong>
— 図が込み入っている場合はこちらを正としてください</summary>

| ノード ID | ラベル | プロパティ |
| --- | --- | --- |
| Album #1 | Album | `name`: Neon Echoes, `releasedYear`: 2019 |
| Album #2 | Album | `name`: Paper Skies, `releasedYear`: 2020 |
| Artist #1 | Artist | `alias`: AVS, `name`: Ava Sterling |
| Artist #2 | Artist | `name`: Ethan Brooks |
| Artist #3 | Artist | `alias`: L.Hart, `name`: Liam Hart |
| Artist #4 | Artist | `name`: Mia Collins |
| Artist #5 | Artist | `name`: Noah Wilder |
| Artist #6 | Artist | `alias`: Z.M., `name`: Zoe Monroe |
| Playlist #1 | Playlist | `modifiedAt`: 2025-08-10, `name`: Fresh Finds Mix, `numFollowers`: 1243 |
| Playlist #2 | Playlist | `modifiedAt`: 2025-07-29, `name`: Roadtrip Fuel, `numFollowers`: 982 |
| Pop:Track #1 | Pop:Track | `duration`: 03:28, `name`: City Lights |
| Pop:Track #2 | Pop:Track | `duration`: 03:47, `name`: Fever Dream |
| Rock:Track #1 | Rock:Track | `duration`: 04:12, `name`: Hollow Moon |
| Rock:Track #2 | Rock:Track | `duration`: 03:50, `name`: Running Red |

</details>

<details><summary><strong>エッジ一覧（クリックで展開）</strong>
— 図が込み入っている場合はこちらを正としてください</summary>

| 始点 | エッジラベル | 終点 | プロパティ |
| --- | --- | --- | --- |
| Pop:Track #1 | BELONGS_TO | Album #1 | — |
| Pop:Track #2 | BELONGS_TO | Album #2 | — |
| Rock:Track #1 | BELONGS_TO | Album #1 | — |
| Rock:Track #2 | BELONGS_TO | Album #2 | — |
| Playlist #1 | CONTAINS | Pop:Track #1 | — |
| Playlist #1 | CONTAINS | Rock:Track #1 | — |
| Playlist #2 | CONTAINS | Pop:Track #2 | — |
| Playlist #2 | CONTAINS | Rock:Track #2 | — |
| Artist #1 | PERFORMS | Pop:Track #1 | — |
| Artist #1 | PERFORMS | Rock:Track #1 | — |
| Artist #2 | PERFORMS | Rock:Track #1 | — |
| Artist #3 | PERFORMS | Pop:Track #2 | — |
| Artist #4 | PERFORMS | Pop:Track #2 | — |
| Artist #5 | PERFORMS | Pop:Track #1 | — |
| Artist #5 | PERFORMS | Rock:Track #2 | — |
| Artist #6 | PERFORMS | Rock:Track #2 | — |
| Artist #1 | RELEASED | Album #1 | `date`: 2019-05-21 |
| Artist #3 | RELEASED | Album #1 | `date`: 2021-09-03 |
| Artist #5 | RELEASED | Album #2 | `date`: 2020-06-12 |

</details>

### 候補スキーマ

<table>
  <tr>
    <td align="center" valign="top" width="50%">
      <img src="img/q5-1-schema-A.png" width="420" /><br /><strong>候補 A</strong>
    </td>
    <td align="center" valign="top" width="50%">
      <img src="img/q5-1-schema-B.png" width="420" /><br /><strong>候補 B</strong>
    </td>
  </tr>
  <tr>
    <td align="center" valign="top" width="50%">
      <img src="img/q5-1-schema-C.png" width="420" /><br /><strong>候補 C</strong>
    </td>
    <td align="center" valign="top" width="50%">
      <img src="img/q5-1-schema-D.png" width="420" /><br /><strong>候補 D</strong>
    </td>
  </tr>
</table>

*図はクリックすると原寸で開けます。*


#### 候補スキーマ A

<details><summary><strong>候補 A の型定義一覧（テキスト版・クリックで展開）</strong>
— 図が込み入っている場合はこちらを正としてください</summary>

ノード型:

- `Album {name, releasedYear}`
- `Artist type 1 {alias, name}`
- `Artist type 2 {name}`
- `Pop:Track {duration, name}`

エッジ型（`(始点)-[ラベル {プロパティ}]->(終点)`）:

- `(Pop:Track)-[BELONGS_TO]->(Album)`
- `(Artist type 1)-[EXTENDS]->(Artist type 2)`
- `(Artist type 2)-[EXTENDS]->(Artist type 2)`
- `(Artist type 1)-[PERFORMS]->(Pop:Track)`
- `(Artist type 2)-[PERFORMS]->(Pop:Track)`
- `(Artist type 1)-[RELEASED]->(Album)`
- `(Artist type 2)-[RELEASED]->(Album)`

</details>

#### 候補スキーマ B

<details><summary><strong>候補 B の型定義一覧（テキスト版・クリックで展開）</strong>
— 図が込み入っている場合はこちらを正としてください</summary>

ノード型:

- `Album {name, releasedYear}`
- `Artist {name, alias?}`
- `Playlist {modifiedAt, name, numFollowers}`
- `Pop {duration, name}`
- `Rock {duration, name}`
- `Track {}`

エッジ型（`(始点)-[ラベル {プロパティ}]->(終点)`）:

- `(Pop)-[BELONGS_TO]->(Album)`
- `(Rock)-[BELONGS_TO]->(Album)`
- `(Playlist)-[CONTAINS]->(Pop)`
- `(Playlist)-[CONTAINS]->(Rock)`
- `(Pop)-[EXTENDS]->(Track)`
- `(Rock)-[EXTENDS]->(Track)`
- `(Artist)-[PERFORMS]->(Pop)`
- `(Artist)-[PERFORMS]->(Rock)`
- `(Artist)-[RELEASED {date}]->(Album)`

</details>

#### 候補スキーマ C

<details><summary><strong>候補 C の型定義一覧（テキスト版・クリックで展開）</strong>
— 図が込み入っている場合はこちらを正としてください</summary>

ノード型:

- `Album {name, releasedYear}`
- `Artist {name, alias?}`
- `Playlist {modifiedAt, name, numFollowers}`
- `Pop:Track {duration, name}`
- `Rock:Track {duration, name}`

エッジ型（`(始点)-[ラベル {プロパティ}]->(終点)`）:

- `(Artist)-[BELONGS_TO]->(Album)`
- `(Artist)-[BELONGS_TO]->(Rock:Track)`
- `(Pop:Track)-[BELONGS_TO]->(Album)`
- `(Pop:Track)-[BELONGS_TO]->(Rock:Track)`
- `(Rock:Track)-[BELONGS_TO]->(Album)`
- `(Artist)-[CONTAINS]->(Pop:Track)`
- `(Artist)-[CONTAINS]->(Rock:Track)`
- `(Playlist)-[CONTAINS]->(Pop:Track)`
- `(Playlist)-[CONTAINS]->(Rock:Track)`
- `(Artist)-[PERFORMS]->(Album)`
- `(Artist)-[PERFORMS]->(Pop:Track)`
- `(Artist)-[PERFORMS]->(Rock:Track)`
- `(Playlist)-[PERFORMS]->(Pop:Track)`
- `(Playlist)-[PERFORMS]->(Rock:Track)`
- `(Pop:Track)-[PERFORMS]->(Album)`
- `(Pop:Track)-[PERFORMS]->(Rock:Track)`
- `(Artist)-[RELEASED {date}]->(Album)`

</details>

#### 候補スキーマ D

<details><summary><strong>候補 D の型定義一覧（テキスト版・クリックで展開）</strong>
— 図が込み入っている場合はこちらを正としてください</summary>

ノード型:

- `Album {name, releasedYear}`
- `Artist {name, alias?}`
- `Playlist {modifiedAt, name, numFollowers}`
- `Pop:Track {duration, name}`
- `Rock:Track {duration, name}`

エッジ型（`(始点)-[ラベル {プロパティ}]->(終点)`）:

- `(Pop:Track)-[BELONGS_TO]->(Album)`
- `(Rock:Track)-[BELONGS_TO]->(Album)`
- `(Playlist)-[CONTAINS]->(Pop:Track)`
- `(Playlist)-[CONTAINS]->(Rock:Track)`
- `(Artist)-[PERFORMS]->(Pop:Track)`
- `(Artist)-[PERFORMS]->(Rock:Track)`
- `(Artist)-[RELEASED {date}]->(Album)`

</details>


---

## タスク2（Q5-2）: 学術文献

### データ

<div align="center"><img src="img/q5-2-instance.png" width="820" /></div>

<details><summary><strong>ノード一覧（クリックで展開）</strong></summary>

| ノード ID | ラベル | プロパティ |
| --- | --- | --- |
| Conference:Venue #1 | Conference:Venue | `name`: Quantum Data Communications, `year`: 2021 |
| Conference:Venue #2 | Conference:Venue | `name`: Symposium on Artificial Minds, `year`: 2020 |
| Industry:Institution #1 | Industry:Institution | `name`: Lumen Tech Labs |
| Industry:Institution #2 | Industry:Institution | `name`: Orion Medical Center |
| Institution:ResearchInstitute #1 | Institution:ResearchInstitute | `name`: Aurora Research Institute |
| Institution:University #1 | Institution:University | `name`: Helios Institute of Science |
| Journal:Venue #1 | Journal:Venue | `issue`: 3, `name`: Journal of Sustainable Robotics, `volume`: 12 |
| Paper #1 | Paper | `title`: Adaptive Healthcare Systems, `year`: 2019 |
| Paper #2 | Paper | `doi`: 10.5555/eeg.2021.077, `title`: Efficient Energy Grids, `year`: 2021 |
| Paper #3 | Paper | `doi`: 10.5555/nim.2018.031, `title`: Nanotechnology in Medicine, `year`: 2018 |
| Paper #4 | Paper | `doi`: 10.5555/npam.2020.001, `title`: Neural Pathways in Artificial Minds, `year`: 2020 |
| Paper #5 | Paper | `doi`: 10.5555/qbdt.2021.042, `title`: Quantum-Based Data Transmission, `year`: 2021 |
| Paper #6 | Paper | `doi`: 10.5555/srd.2022.010, `title`: Sustainable Robotics Design, `year`: 2022 |
| Person #1 | Person | `name`: Alice Tanaka, `orcid`: 0000-0001-2345-6789 |
| Person #2 | Person | `name`: Brian Lee |
| Person #3 | Person | `name`: Clara Suzuki, `orcid`: 0000-0002-1111-2222 |
| Person #4 | Person | `name`: Elena Nakamura, `orcid`: 0000-0003-3333-4444 |

</details>

<details><summary><strong>エッジ一覧（クリックで展開）</strong></summary>

| 始点 | エッジラベル | 終点 | プロパティ |
| --- | --- | --- | --- |
| Person #1 | AFFILIATED_WITH | Institution:ResearchInstitute #1 | `from`: 2018-04, `to`: 2021-03 |
| Person #1 | AFFILIATED_WITH | Institution:University #1 | `from`: 2016-04, `to`: 2021-09 |
| Person #2 | AFFILIATED_WITH | Industry:Institution #1 | `from`: 2019-06, `to`: 2023-03 |
| Person #2 | AFFILIATED_WITH | Institution:University #1 | `from`: 2019-04 |
| Person #3 | AFFILIATED_WITH | Institution:ResearchInstitute #1 | `from`: 2017-10 |
| Person #4 | AFFILIATED_WITH | Industry:Institution #2 | `from`: 2020-01 |
| Person #1 | AUTHORED | Paper #1 | `authorIndex`: 2 |
| Person #1 | AUTHORED | Paper #3 | `authorIndex`: 1 |
| Person #1 | AUTHORED | Paper #5 | `authorIndex`: 1 |
| Person #2 | AUTHORED | Paper #1 | `authorIndex`: 1 |
| Person #2 | AUTHORED | Paper #4 | `authorIndex`: 1 |
| Person #3 | AUTHORED | Paper #4 | `authorIndex`: 2 |
| Person #3 | AUTHORED | Paper #6 | `authorIndex`: 1 |
| Person #4 | AUTHORED | Paper #2 | `authorIndex`: 1 |
| Paper #1 | CITES | Paper #6 | — |
| Paper #2 | CITES | Paper #5 | — |
| Paper #3 | CITES | Paper #5 | — |
| Paper #4 | CITES | Paper #1 | — |
| Paper #5 | CITES | Paper #4 | — |
| Paper #6 | CITES | Paper #4 | — |
| Paper #1 | PUBLISHED_IN | Conference:Venue #2 | — |
| Paper #2 | PUBLISHED_IN | Journal:Venue #1 | — |
| Paper #3 | PUBLISHED_IN | Journal:Venue #1 | — |
| Paper #4 | PUBLISHED_IN | Conference:Venue #2 | — |
| Paper #5 | PUBLISHED_IN | Conference:Venue #1 | — |
| Paper #6 | PUBLISHED_IN | Conference:Venue #1 | — |

</details>

### 候補スキーマ

<table>
  <tr>
    <td align="center" valign="top" width="50%">
      <img src="img/q5-2-schema-A.png" width="420" /><br /><strong>候補 A</strong>
    </td>
    <td align="center" valign="top" width="50%">
      <img src="img/q5-2-schema-B.png" width="420" /><br /><strong>候補 B</strong>
    </td>
  </tr>
  <tr>
    <td align="center" valign="top" width="50%">
      <img src="img/q5-2-schema-C.png" width="420" /><br /><strong>候補 C</strong>
    </td>
    <td align="center" valign="top" width="50%">
      <img src="img/q5-2-schema-D.png" width="420" /><br /><strong>候補 D</strong>
    </td>
  </tr>
</table>

*図はクリックすると原寸で開けます。*


#### 候補スキーマ A

<details><summary><strong>候補 A の型定義一覧（テキスト版・クリックで展開）</strong></summary>

ノード型:

- `Conference:Venue {name, year}`
- `Industry:Institution {name}`
- `Institution:ResearchInstitute {name}`
- `Institution:University {name}`
- `Journal:Venue {issue, name, volume}`
- `Paper {title, year, doi?}`
- `Person {name, orcid?}`

エッジ型（`(始点)-[ラベル {プロパティ}]->(終点)`）:

- `(Person)-[AFFILIATED_WITH {from, to?}]->(Industry:Institution)`
- `(Person)-[AFFILIATED_WITH {from, to?}]->(Institution:ResearchInstitute)`
- `(Person)-[AFFILIATED_WITH {from, to?}]->(Institution:University)`
- `(Person)-[AUTHORED {authorIndex}]->(Paper)`
- `(Paper)-[CITES]->(Paper)`
- `(Paper)-[PUBLISHED_IN]->(Conference:Venue)`
- `(Paper)-[PUBLISHED_IN]->(Journal:Venue)`

</details>

#### 候補スキーマ B

<details><summary><strong>候補 B の型定義一覧（テキスト版・クリックで展開）</strong></summary>

ノード型:

- `Conference:Venue {name, year}`
- `Industry:Institution {name}`
- `Institution:ResearchInstitute {name}`
- `Institution:University {name}`
- `Journal:Venue {issue, name, volume}`
- `Paper {title, year, doi?}`
- `Person {name, orcid?}`

エッジ型（`(始点)-[ラベル {プロパティ}]->(終点)`）:

- `(Person)-[AFFILIATED_WITH {authorIndex?, from?, to?}]->(Industry:Institution)`
- `(Person)-[AFFILIATED_WITH {authorIndex?, from?, to?}]->(Institution:ResearchInstitute)`
- `(Person)-[AFFILIATED_WITH {authorIndex?, from?, to?}]->(Institution:University)`
- `(Person)-[AFFILIATED_WITH {authorIndex?, from?, to?}]->(Paper)`
- `(Person)-[AUTHORED {authorIndex?, from?, to?}]->(Industry:Institution)`
- `(Person)-[AUTHORED {authorIndex?, from?, to?}]->(Institution:ResearchInstitute)`
- `(Person)-[AUTHORED {authorIndex?, from?, to?}]->(Institution:University)`
- `(Person)-[AUTHORED {authorIndex?, from?, to?}]->(Paper)`
- `(Paper)-[CITES]->(Conference:Venue)`
- `(Paper)-[CITES]->(Journal:Venue)`
- `(Paper)-[CITES]->(Paper)`
- `(Paper)-[PUBLISHED_IN]->(Conference:Venue)`
- `(Paper)-[PUBLISHED_IN]->(Journal:Venue)`
- `(Paper)-[PUBLISHED_IN]->(Paper)`

</details>

#### 候補スキーマ C

<details><summary><strong>候補 C の型定義一覧（テキスト版・クリックで展開）</strong></summary>

ノード型:

- `Conference:Venue {name, year}`
- `Industry:Institution {name}`
- `Paper type 1 {doi, title, year}`
- `Paper type 2 {title, year}`
- `Person type 1 {name}`
- `Person type 2 {name, orcid}`

エッジ型（`(始点)-[ラベル {プロパティ}]->(終点)`）:

- `(Person type 1)-[AFFILIATED_WITH]->(Industry:Institution)`
- `(Person type 2)-[AFFILIATED_WITH]->(Industry:Institution)`
- `(Person type 1)-[AUTHORED]->(Paper type 1)`
- `(Person type 1)-[AUTHORED]->(Paper type 2)`
- `(Person type 2)-[AUTHORED]->(Paper type 1)`
- `(Person type 2)-[AUTHORED]->(Paper type 2)`
- `(Paper type 1)-[CITES]->(Paper type 1)`
- `(Paper type 1)-[CITES]->(Paper type 2)`
- `(Paper type 2)-[CITES]->(Paper type 1)`
- `(Paper type 1)-[EXTENDS]->(Paper type 2)`
- `(Paper type 2)-[EXTENDS]->(Paper type 2)`
- `(Person type 1)-[EXTENDS]->(Person type 1)`
- `(Person type 2)-[EXTENDS]->(Person type 1)`
- `(Paper type 1)-[PUBLISHED_IN]->(Conference:Venue)`
- `(Paper type 2)-[PUBLISHED_IN]->(Conference:Venue)`

</details>

#### 候補スキーマ D

<details><summary><strong>候補 D の型定義一覧（テキスト版・クリックで展開）</strong></summary>

ノード型:

- `Conference {name, year}`
- `Industry {name}`
- `Institution {}`
- `Journal {issue, name, volume}`
- `Paper {title, year, doi?}`
- `Person {name, orcid?}`
- `ResearchInstitute {name}`
- `University {name}`
- `Venue {}`

エッジ型（`(始点)-[ラベル {プロパティ}]->(終点)`）:

- `(Person)-[AFFILIATED_WITH {from, to?}]->(Industry)`
- `(Person)-[AFFILIATED_WITH {from, to?}]->(ResearchInstitute)`
- `(Person)-[AFFILIATED_WITH {from, to?}]->(University)`
- `(Person)-[AUTHORED {authorIndex}]->(Paper)`
- `(Paper)-[CITES]->(Paper)`
- `(Conference)-[EXTENDS]->(Venue)`
- `(Industry)-[EXTENDS]->(Institution)`
- `(Journal)-[EXTENDS]->(Venue)`
- `(ResearchInstitute)-[EXTENDS]->(Institution)`
- `(University)-[EXTENDS]->(Institution)`
- `(Paper)-[PUBLISHED_IN]->(Conference)`
- `(Paper)-[PUBLISHED_IN]->(Journal)`

</details>


---

## タスク3（Q5-3）: EC（電子商取引）

### データ

<div align="center"><img src="img/q5-3-instance.png" width="820" /></div>

<details><summary><strong>ノード一覧（クリックで展開）</strong></summary>

| ノード ID | ラベル | プロパティ |
| --- | --- | --- |
| Customer #1 | Customer | `customer_id`: CUC1, `email`: contact@acorn.example, `name`: Acorn LLC, `phone`: +1-202-555-0101, `type`: Company |
| Customer #2 | Customer | `customer_id`: CUP2, `email`: bob@example.com, `name`: Bob Smith, `type`: Person |
| Customer #3 | Customer | `customer_id`: CUC2, `email`: hello@bright.example, `name`: Bright Co., `type`: Company |
| Customer #4 | Customer | `customer_id`: CUC4, `email`: info@delta.example, `name`: Delta Group, `type`: Company |
| Order #1 | Order | `order_date`: 2025-06-03, `order_id`: O1, `status`: shipped |
| Order #2 | Order | `order_date`: 2025-06-05, `order_id`: O2, `status`: pending |
| Order #3 | Order | `order_date`: 2025-06-08, `order_id`: O3, `status`: canceled |
| Product #1 | Product | `name`: Drip Coffee Set, `price`: 45, `product_id`: P6 |
| Product #2 | Product | `description`: Soft case, `name`: Phone Case X, `price`: 19, `product_id`: P3 |
| Product #3 | Product | `name`: Screen Protector, `price`: 12, `product_id`: P10 |
| Product #4 | Product | `description`: Entry smartphone, `name`: Smartphone A, `price`: 699, `product_id`: P1 |
| Product #5 | Product | `name`: Smartphone B, `price`: 899, `product_id`: P2 |
| Product #6 | Product | `name`: Wireless Charger, `price`: 39, `product_id`: P4 |
| Region #1 | Region | `name`: Kansai, `region_id`: R2 |
| Region #2 | Region | `name`: Kanto, `region_id`: R1 |
| Supplier #1 | Supplier | `name`: Alpha Supply, `rating`: 5, `supplier_id`: S1 |
| Supplier #2 | Supplier | `name`: Beta Traders, `rating`: 4, `supplier_id`: S2 |

</details>

<details><summary><strong>エッジ一覧（クリックで展開）</strong></summary>

| 始点 | エッジラベル | 終点 | プロパティ |
| --- | --- | --- | --- |
| Product #4 | FREQUENTLY_BOUGHT_WITH | Product #2 | — |
| Product #5 | FREQUENTLY_BOUGHT_WITH | Product #6 | — |
| Order #1 | HAS_LINE_ITEM | Product #2 | `quantity`: 2 |
| Order #1 | HAS_LINE_ITEM | Product #4 | `quantity`: 1 |
| Order #2 | HAS_LINE_ITEM | Product #5 | `quantity`: 1 |
| Order #3 | HAS_LINE_ITEM | Product #6 | `quantity`: 1 |
| Customer #2 | LIVES_IN | Region #1 | — |
| Customer #1 | LOCATED_IN | Region #2 | — |
| Customer #3 | LOCATED_IN | Region #1 | — |
| Customer #4 | LOCATED_IN | Region #2 | — |
| Product #1 | MADE_IN | Region #2 | — |
| Product #4 | MADE_IN | Region #2 | — |
| Product #5 | MADE_IN | Region #1 | — |
| Supplier #1 | PARTNERS_WITH | Supplier #2 | — |
| Customer #1 | PLACES_ORDER | Order #1 | `channel`: web |
| Customer #2 | PLACES_ORDER | Order #2 | — |
| Customer #3 | PLACES_ORDER | Order #3 | `channel`: phone |
| Supplier #1 | SUPPLIES | Product #3 | — |
| Supplier #1 | SUPPLIES | Product #4 | — |
| Supplier #2 | SUPPLIES | Product #5 | — |

</details>

### 候補スキーマ

<table>
  <tr>
    <td align="center" valign="top" width="50%">
      <img src="img/q5-3-schema-A.png" width="420" /><br /><strong>候補 A</strong>
    </td>
    <td align="center" valign="top" width="50%">
      <img src="img/q5-3-schema-B.png" width="420" /><br /><strong>候補 B</strong>
    </td>
  </tr>
  <tr>
    <td align="center" valign="top" width="50%">
      <img src="img/q5-3-schema-C.png" width="420" /><br /><strong>候補 C</strong>
    </td>
    <td align="center" valign="top" width="50%">
      <img src="img/q5-3-schema-D.png" width="420" /><br /><strong>候補 D</strong>
    </td>
  </tr>
</table>

*図はクリックすると原寸で開けます。*

※ **候補 A と B は図の見た目がほぼ同じです。** 両者の違いは `PLACES_ORDER` エッジ型のプロパティ `channel` の扱いだけで、**A では必須（`{channel}`）、B では任意（`{channel?}`）** です。それ以外のノード型・エッジ型はすべて同一です（2 つの図で `LIVES_IN` と `LOCATED_IN` の描画位置が入れ替わっていますが、どちらも `(Customer)-[...]->(Region)` で内容に違いはありません）。


#### 候補スキーマ A

<details><summary><strong>候補 A の型定義一覧（テキスト版・クリックで展開）</strong></summary>

ノード型:

- `Customer {customer_id, email, name, type, phone?}`
- `Order {order_date, order_id, status}`
- `Product {name, price, product_id, description?}`
- `Region {name, region_id}`
- `Supplier {name, rating, supplier_id}`

エッジ型（`(始点)-[ラベル {プロパティ}]->(終点)`）:

- `(Product)-[FREQUENTLY_BOUGHT_WITH]->(Product)`
- `(Order)-[HAS_LINE_ITEM {quantity}]->(Product)`
- `(Customer)-[LIVES_IN]->(Region)`
- `(Customer)-[LOCATED_IN]->(Region)`
- `(Product)-[MADE_IN]->(Region)`
- `(Supplier)-[PARTNERS_WITH]->(Supplier)`
- `(Customer)-[PLACES_ORDER {channel}]->(Order)`
- `(Supplier)-[SUPPLIES]->(Product)`

</details>

#### 候補スキーマ B

<details><summary><strong>候補 B の型定義一覧（テキスト版・クリックで展開）</strong></summary>

ノード型:

- `Customer {customer_id, email, name, type, phone?}`
- `Order {order_date, order_id, status}`
- `Product {name, price, product_id, description?}`
- `Region {name, region_id}`
- `Supplier {name, rating, supplier_id}`

エッジ型（`(始点)-[ラベル {プロパティ}]->(終点)`）:

- `(Product)-[FREQUENTLY_BOUGHT_WITH]->(Product)`
- `(Order)-[HAS_LINE_ITEM {quantity}]->(Product)`
- `(Customer)-[LIVES_IN]->(Region)`
- `(Customer)-[LOCATED_IN]->(Region)`
- `(Product)-[MADE_IN]->(Region)`
- `(Supplier)-[PARTNERS_WITH]->(Supplier)`
- `(Customer)-[PLACES_ORDER {channel?}]->(Order)`
- `(Supplier)-[SUPPLIES]->(Product)`

</details>

#### 候補スキーマ C

※ この候補はエッジ型が多いため、**図中のエッジラベルを省略しています**。エッジ型の内容は下の型定義一覧（テキスト版）でご確認ください。

<details><summary><strong>候補 C の型定義一覧（テキスト版・クリックで展開）</strong></summary>

ノード型:

- `Customer {customer_id, email, name, type, phone?}`
- `Order {order_date, order_id, status}`
- `Product {name, price, product_id, description?}`
- `Region {name, region_id}`
- `Supplier {name, rating, supplier_id}`

エッジ型（`(始点)-[ラベル {プロパティ}]->(終点)`）:

- `(Product)-[FREQUENTLY_BOUGHT_WITH]->(Product)`
- `(Customer)-[HAS_LINE_ITEM {channel?, quantity?}]->(Order)`
- `(Customer)-[HAS_LINE_ITEM {channel?, quantity?}]->(Product)`
- `(Order)-[HAS_LINE_ITEM {channel?, quantity?}]->(Order)`
- `(Order)-[HAS_LINE_ITEM {channel?, quantity?}]->(Product)`
- `(Customer)-[LIVES_IN]->(Region)`
- `(Customer)-[LOCATED_IN]->(Product)`
- `(Customer)-[LOCATED_IN]->(Region)`
- `(Customer)-[LOCATED_IN]->(Supplier)`
- `(Product)-[LOCATED_IN]->(Product)`
- `(Product)-[LOCATED_IN]->(Region)`
- `(Product)-[LOCATED_IN]->(Supplier)`
- `(Supplier)-[LOCATED_IN]->(Product)`
- `(Supplier)-[LOCATED_IN]->(Region)`
- `(Supplier)-[LOCATED_IN]->(Supplier)`
- `(Customer)-[MADE_IN]->(Product)`
- `(Customer)-[MADE_IN]->(Region)`
- `(Customer)-[MADE_IN]->(Supplier)`
- `(Product)-[MADE_IN]->(Product)`
- `(Product)-[MADE_IN]->(Region)`
- `(Product)-[MADE_IN]->(Supplier)`
- `(Supplier)-[MADE_IN]->(Product)`
- `(Supplier)-[MADE_IN]->(Region)`
- `(Supplier)-[MADE_IN]->(Supplier)`
- `(Customer)-[PARTNERS_WITH]->(Product)`
- `(Customer)-[PARTNERS_WITH]->(Region)`
- `(Customer)-[PARTNERS_WITH]->(Supplier)`
- `(Product)-[PARTNERS_WITH]->(Product)`
- `(Product)-[PARTNERS_WITH]->(Region)`
- `(Product)-[PARTNERS_WITH]->(Supplier)`
- `(Supplier)-[PARTNERS_WITH]->(Product)`
- `(Supplier)-[PARTNERS_WITH]->(Region)`
- `(Supplier)-[PARTNERS_WITH]->(Supplier)`
- `(Customer)-[PLACES_ORDER {channel?, quantity?}]->(Order)`
- `(Customer)-[PLACES_ORDER {channel?, quantity?}]->(Product)`
- `(Order)-[PLACES_ORDER {channel?, quantity?}]->(Order)`
- `(Order)-[PLACES_ORDER {channel?, quantity?}]->(Product)`
- `(Customer)-[SUPPLIES]->(Product)`
- `(Customer)-[SUPPLIES]->(Region)`
- `(Customer)-[SUPPLIES]->(Supplier)`
- `(Product)-[SUPPLIES]->(Product)`
- `(Product)-[SUPPLIES]->(Region)`
- `(Product)-[SUPPLIES]->(Supplier)`
- `(Supplier)-[SUPPLIES]->(Product)`
- `(Supplier)-[SUPPLIES]->(Region)`
- `(Supplier)-[SUPPLIES]->(Supplier)`

</details>

#### 候補スキーマ D

<details><summary><strong>候補 D の型定義一覧（テキスト版・クリックで展開）</strong></summary>

ノード型:

- `Customer type 1 {customer_id, email, name, phone, type}`
- `Customer type 2 {customer_id, email, name, type}`
- `Product type 1 {description, name, price, product_id}`
- `Product type 2 {name, price, product_id}`
- `Region {name, region_id}`
- `Supplier {name, rating, supplier_id}`

エッジ型（`(始点)-[ラベル {プロパティ}]->(終点)`）:

- `(Customer type 1)-[EXTENDS]->(Customer type 2)`
- `(Customer type 2)-[EXTENDS]->(Customer type 2)`
- `(Product type 1)-[EXTENDS]->(Product type 2)`
- `(Product type 2)-[EXTENDS]->(Product type 2)`
- `(Product type 1)-[FREQUENTLY_BOUGHT_WITH]->(Product type 1)`
- `(Product type 2)-[FREQUENTLY_BOUGHT_WITH]->(Product type 2)`
- `(Customer type 2)-[LIVES_IN]->(Region)`
- `(Customer type 1)-[LOCATED_IN]->(Region)`
- `(Customer type 2)-[LOCATED_IN]->(Region)`
- `(Product type 1)-[MADE_IN]->(Region)`
- `(Product type 2)-[MADE_IN]->(Region)`
- `(Supplier)-[PARTNERS_WITH]->(Supplier)`
- `(Supplier)-[SUPPLIES]->(Product type 1)`
- `(Supplier)-[SUPPLIES]->(Product type 2)`

</details>


---

## おわりに

問題は以上です。ご回答は Google Form から送信してください。

お忙しいところ、最後までご協力いただきありがとうございました。
いただいた回答は、スキーマ評価指標の妥当性を確認する目的にのみ使用します。

---
