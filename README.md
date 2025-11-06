Multicast Chat (Python)
========================

Este pequeno aplicativo permite que dois (ou mais) computadores na mesma rede local troquem mensagens usando multicast UDP.

Arquivos
- `multicast_chat.py` - script principal (Python 3)

Requisitos
- Python 3.6+ (testado com 3.8+)
- Rede local que permita tráfego UDP multicast entre as máquinas. Verifique firewall/antivírus.

Uso
1. Em cada máquina, abra um terminal e execute:

```bash
python multicast_chat.py --name PC1
```

Substitua `PC1` por um nome para identificar a máquina.

2. Repita em outra máquina:

```bash
python multicast_chat.py --name PC2
```

3. Digite mensagens e pressione Enter para enviar. As mensagens aparecerão em todas as máquinas inscritas no mesmo grupo e porta.

Opções úteis
- `--group` - endereço do grupo multicast (padrão: `224.0.0.1`)
- `--port` - porta UDP (padrão: `5007`)
- `--ttl` - alcance do multicast (padrão: `1`)

Notas sobre network/firewall
- Em muitas redes domésticas, multicast UDP trafega normalmente. Em redes corporativas pode ser bloqueado.
- Abra/permita UDP na porta escolhida (ex.: 5007) no firewall local.

Testes locais (mesma máquina)
- Você pode executar o script em duas janelas de terminal na mesma máquina. Em alguns sistemas você pode receber suas próprias mensagens devido ao loopback; o script tenta evitar eco usando um identificador único.

Problemas comuns
- Se não receber mensagens: verifique se as duas instâncias usam o mesmo `--group` e `--port` e se não há regras de firewall bloqueando UDP.

Licença
- Código de exemplo, livre para usar e adaptar.
