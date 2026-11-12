# Sistema de KPIs de Sistemas Fotovoltaicos

Armazena as leituras mensais de geração dos sistemas fotovoltaicos e exporta um
relatório em PDF para qualquer período selecionado.

O relatório tem três páginas de conteúdo mais o anexo: a primeira traz os
indicadores do período e a geração mês a mês; a segunda, as perdas por
inoperância, a disponibilidade e o desempenho de cada unidade; a terceira, o
desdobramento financeiro e ambiental; o anexo reúne o registro fotográfico das
vistorias.

A cor carrega informação. Cada grupo de sistemas tem uma família cromática e
cada unidade recebe um tom dentro dela, de modo que a origem da geração é
legível sem consultar a legenda. O verde identifica o que foi gerado e o latão,
o que foi perdido por inoperância.

Nenhum indicador derivado é gravado no banco. Economia e emissões são sempre
recalculadas a partir da energia e dos parâmetros do mês correspondente, de
modo que relatórios antigos permanecem coerentes com a metodologia vigente na
época de cada competência.

## O aplicativo

O caminho mais curto é abrir o aplicativo e trabalhar por ele. No Windows, duplo
clique em `executar.bat`; no Linux ou no macOS, `./executar.sh`. Na primeira
execução o atalho cria o ambiente virtual e instala as dependências, depois abre
a interface no navegador.

A barra lateral mostra o intervalo de leituras já importadas e recebe a planilha
nova. As quatro abas cobrem o ciclo completo:

- **Relatório**: escolha das competências e dos grupos, indicadores do período,
  tabela de desempenho por unidade, edição dos comentários e geração do PDF, com
  opção de ver as páginas na própria tela antes de baixar.
- **Leituras e parâmetros**: lançamento manual de uma leitura e edição da tarifa
  fora ponta e do fator de emissão de cada mês.
- **Vistorias**: envio das fotos com legenda e unidade, que montam o anexo.
- **Unidades**: grupo, potência, área, ordem e participação no painel.

## Instalação

### Publicação com armazenamento persistente

O repositório inclui `Dockerfile` e `render.yaml` para executar o aplicativo
completo no Render, com banco SQLite, fotos e relatórios em um disco persistente
de 1 GB. O plano configurado é **Starter (pago)**. Confira o custo apresentado
pelo Render antes de confirmar a criação do serviço.

[Publicar no Render](https://render.com/deploy?repo=https://github.com/atnee/dashboard-kpis)

1. Conecte sua conta do Render ao GitHub e abra o link acima.
2. Defina `KPI_ACCESS_PASSWORD` com uma senha forte e exclusiva. Não grave a
   senha no código nem a compartilhe no repositório.
3. Confira o plano e o disco e confirme a publicação.
4. Abra o endereço HTTPS exibido pelo Render e entre com a senha definida.
5. Importe `dados/kpis_energia_por_unidade.xlsx` na barra lateral para carregar
   as leituras iniciais. A planilha está disponível neste repositório.

O endereço final é atribuído pelo Render e só estará disponível depois que a
publicação terminar. GitHub Pages não executa este aplicativo Python.

`KPI_STORAGE_DIR=/app/storage` direciona todos os arquivos gerados para o volume
persistente. Atualizações do código preservam esses dados; excluir o disco ou
o serviço pode removê-los. Faça cópias de segurança periódicas do volume, com
o aplicativo parado ou usando a API de backup do SQLite para o banco.
O disco exige uma única instância do aplicativo. A senha dá acesso completo
ao painel, incluindo edição; compartilhe-a apenas com a equipe autorizada.

Para executar em outro servidor com Docker:

```bash
docker build -t dashboard-kpis .
docker run --env-file .env -p 8501:8501 -v kpi-data:/app/storage dashboard-kpis
```

Crie `.env` localmente com `KPI_STORAGE_DIR=/app/storage`,
`KPI_REQUIRE_AUTH=1` e `KPI_ACCESS_PASSWORD` com a senha escolhida.
O arquivo `.env` é ignorado pelo Git. Ao publicar fora do Render, configure
HTTPS no servidor. Os atalhos locais continuam funcionando sem senha por padrão.

### Execução local

```bash
pip install -r requirements.txt
```

O WeasyPrint depende das bibliotecas de sistema Pango, Cairo e GDK-PixBuf. No
Ubuntu e no Debian:

```bash
sudo apt install libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf-2.0-0
```

No Windows, a instalação do GTK Runtime resolve a mesma dependência.

## Uso pela linha de comando

A linha de comando serve para rotina e automação, por exemplo em uma tarefa
agendada que reemite o relatório do mês.

```bash
python cli.py importar dados/kpis_energia_por_unidade.xlsx
python cli.py periodo
python cli.py gerar --inicio 2025-01 --fim 2026-02 --saida saida/kpi.pdf
python cli.py listar
python cli.py exportar --id 1 --saida saida/kpi_reemitido.pdf
```

A opção `--logo caminho/logo.png` insere a marca no cabeçalho das duas páginas.

## Estrutura

```
kpi_fv/
  db.py            esquema SQLite, cadastro padrão e resolução de apelidos
  importador.py    leitura das abas photovoltaic e photovoltaic_loss
  calculo.py       séries mensais, totais por grupo, inoperância
  tema.py          paleta por grupo, tipografia e estilo dos gráficos
  graficos.py      barras empilhadas, linha de total e disponibilidade
  comentarios.py   rascunho dos comentários a partir dos números
  relatorio.py     persistência do relatório, HTML e exportação em PDF
  formato.py       formatação numérica em padrão brasileiro
  templates/       painel.html
  static/          estilo.css
app.py             aplicativo Streamlit
cli.py             linha de comando
executar.sh        atalho de execução no Linux e no macOS
executar.bat       atalho de execução no Windows
.streamlit/        tema do aplicativo
```

## Modelo de dados

| Tabela | Conteúdo |
|---|---|
| `grupo` | Prefeitura do Campus, Projeto SIMA, E-MOB, CEAMAZON |
| `unidade` | nome, grupo, capacidade, área, cor, participação no painel |
| `alias_unidade` | apelidos que apontam para a mesma unidade |
| `parametro_mensal` | tarifa fora ponta e fator de emissão por competência |
| `leitura` | energia por unidade, competência e tipo (gerada ou perdida) |
| `relatorio` | período, título, equipe, autor, revisor, datas |
| `comentario` | comentários do relatório, na ordem de exibição |
| `foto` | fotos de vistoria do Anexo I, com seção e legenda |

## Importação da planilha

O importador aceita o formato atual das abas `photovoltaic` e
`photovoltaic_loss`: uma linha por competência, uma coluna por unidade e as
colunas de tarifa e fator de emissão ao final. As linhas de totais anuais que
ficam abaixo da série mensal são descartadas pela validação da data, e as
colunas `Total`, `Economia` e `Redução de Gases` são ignoradas porque esses
valores são recalculados.

Variações de grafia encontradas nos arquivos existentes (`PRODENA` e
`PRODERNA`, `Mirate` e `Mirante`, `Mirate do Rio - SIMA` e
`WEG - Mirante do Rio`) são resolvidas pela tabela de apelidos, para que uma
unidade não apareça duplicada. Uma coluna desconhecida gera uma unidade nova e
um aviso ao final da importação.

## Pontos de atenção

As unidades do CEAMAZON (Controlador de Carga, Fronius, SMA e Sistema de
Armazenamento) entram com `incluir_painel = 0`: elas aparecem apenas nos
gráficos de geração perdida, reproduzindo o comportamento do painel atual.

A classificação das perdas do Mirante do Rio difere entre os arquivos
existentes: na geração ele é contabilizado no Projeto SIMA, enquanto nas perdas
o painel antigo o soma à Prefeitura do Campus. O padrão adotado aqui mantém a
unidade sempre no Projeto SIMA. A aba de cadastro permite mudar o grupo de
qualquer unidade caso a convenção da equipe seja outra.

Uma unidade é considerada inoperante em uma competência quando a geração fica
igual ou abaixo de 1 kWh. O limite está em `calculo.unidades_inoperantes` e
alimenta o comentário automático sobre sistemas parados.
