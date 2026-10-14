# enem-analise-erros: Analisador de Erros do ENEM (Prova Azul)
Código em Python para analisar os microdados oficiais do ENEM, calculando taxas de erro por questão na prova azul. Desenvolvido para o projeto PIBIC.

## Descrição do Projeto

Este repositório contém um script em Python desenvolvido para *ler os arquivos de itens da prova* e *processar os microdados oficiais do ENEM* para **mapear o desempenho detalhado de cada questão** (calculando a taxa de erro, acerto e abstenção por questão), focando especificamente na prova de cor **AZUL** na aplicação regular. 

Apesar de todas as edições do ENEM estarem aptas a serem analisadas por esse código, o foco da pesquisa incluirá a análise dos últimos 10 anos, ou seja, das edições de **2015 até 2025**.

### Principais funcionalidades

- **Filtragem automática** da prova azul para cada área de conhecimento (Linguagens e Códigos, Ciências Humanas, Ciências da Natureza e Matemática).
- Tratamento adequado para a divisão de língua estrangeira (inglês e espanhol) na prova de Linguagens.
- **Cálculo da porcentagem** de acertos, erros e marcações em branco ou dupla marcação por item.
- Extração de parâmetros da **TRI** (*Teoria de Resposta ao Item*), como dificuldade e discriminação, quando disponíveis.
- Consolidação de múltiplos anos em uma única tabela e geração automática de um ranking com as questões mais difíceis.

## Requisitos

Para rodar este código, será necessário ter o Python 3 instalado, juntamente com as bibliotecas `pandas` e `numpy`. 
Instale as dependências executando o comando a seguir no terminal: 
```text
pip install pandas numpy
```

## Como baixar os dados

Os microdados oficiais do ENEM não estão inclusos neste repositório devido ao grande volume de dados. Para executar o código na sua máquina, siga os passos abaixo:

**1.** Acesse o portal oficial de dados abertos do Inep e baixe os microdados através do link: [Portal de Dados Abertos do Inep](https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/enem).

**2.** Baixe os arquivos de provas/gabaritos do ano desejado por meio do link: [Provas e Gabaritos do Enem](https://www.gov.br/inep/pt-br/areas-de-atuacao/avaliacao-e-exames-educacionais/enem/provas-e-gabaritos).

**3.** Extraia os arquivos e identifique na pasta de dados os seguintes arquivos necessários para a execução:
   - O arquivo de itens da prova (ex: `ITENS_PROVA_2024.csv`).
   - O arquivo de resultados ou microdados gerais (ex: `RESULTADOS_2024.csv` ou `MICRODADOS_ENEM_2024.csv`).

**4.** Salve esses arquivos no diretório do seu projeto ou indique o caminho correto ao executar os comandos pelo terminal.

## Demonstração com a edição de 2024
### Entrada pelo terminal:
```text
python enem_erros.py --ano 2024 --itens ITENS_PROVA_2024.csv --resultados RESULTADOS_2024.csv
```
### Saída/Resultado:
```text
ENEM 2024
  conferência CH/1383: OK, gabarito bate com o do participante
  conferência CN/1373: OK, gabarito bate com o do participante
  conferência CN/1419: OK, gabarito bate com o do participante
  conferência MT/1363: OK, gabarito bate com o do participante
  conferência MT/1407: OK, gabarito bate com o do participante
  4,332,944 linhas lidas...
  total: 4,332,944 linhas; 0 respostas descartadas por tamanho != 45

Provas AZUL encontradas (participantes presentes):
  LC  prova 1395:    788,173
  LC  prova 1441:          0
  LC  prova 1353:          0
  CH  prova 1383:    788,173
  CH  prova 1431:          0
  CH  prova 1343:          0
  CN  prova 1419:    746,854
  CN  prova 1373:         58
  CN  prova 1333:          0
  MT  prova 1407:    746,854
  MT  prova 1363:         58
  MT  prova 1323:          0
Usando a prova com mais participantes em cada área (a regular): {'LC': '1395', 'CH': '1383', 'CN': '1419', 'MT': '1407'}

Salvo em saida\erros_2024.csv (185 linhas). As 10 questões com mais erros:
area  posicao habilidade  pct_erro  dificuldade_tri
  CN       95         11     92.40          2.03104
  CN      115         15     89.15          2.15318
  CH       78         23     88.42          1.97948
  MT      151         11     87.08          2.50442
  CN      103         18     86.95          1.79703
  MT      180          2     84.60          2.42519
  CN      132          5     84.50          2.31700
  MT      136         13     84.08          2.55251
  CH       82          1     83.94          2.16372
  CN       98         16     83.79          1.77477
```
---
### Declaração de Uso de IA

Parte da estruturação do código, validação da lógica de processamento de dados e refinamento da documentação deste projeto contou com o apoio de inteligência artificial (**Claude**, da Anthropic), utilizada como ferramenta de suporte técnico e revisão durante o desenvolvimento.

*Desenvolvido por Laísla Oliveira.*
