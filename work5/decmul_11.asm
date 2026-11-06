; Assembly listing for method System.Decimal+DecCalc:VarDecMul(byref,byref) (Instrumented Tier1)
; Emitting BLENDED_CODE for x64 + VEX on Windows
; Instrumented Tier1 code
; optimized code
; optimized using Synthesized PGO
; rsp based frame
; fully interruptible
; with Synthesized PGO: fgCalledCount is 100
; PGO data available, profile data was all zero
; 0 inlinees with PGO data; 47 single block inlinees; 5 inlinees without PGO data

G_M000_IG01:                ;; offset=0x0000
       push     r14
       push     rdi
       push     rsi
       push     rbp
       push     rbx
       sub      rsp, 64
       mov      rbx, rcx
       mov      rsi, rdx
 
G_M000_IG02:                ;; offset=0x0010
       mov      eax, dword ptr [rbx]
       add      eax, dword ptr [rsi]
       shr      eax, 16
       movzx    rdi, al
       mov      eax, dword ptr [rbx+0x04]
       or       eax, dword ptr [rbx+0x0C]
       je       G_M000_IG23
 
G_M000_IG03:                ;; offset=0x0027
       mov      eax, dword ptr [rsi+0x04]
       or       eax, dword ptr [rsi+0x0C]
       je       G_M000_IG11
 
G_M000_IG04:                ;; offset=0x0033
       mov      rax, qword ptr [rbx+0x08]
       mul      rdx:rax, qword ptr [rsi+0x08]
       mov      rbp, rdx
       mov      qword ptr [rsp+0x28], rax
       mov      ecx, dword ptr [rbx+0x04]
       or       ecx, dword ptr [rsi+0x04]
       jne      SHORT G_M000_IG06
 
G_M000_IG05:                ;; offset=0x004B
       mov      rcx, 0x7FFF3EA930A4
       call     CORINFO_HELP_COUNTPROFILE32
       mov      qword ptr [rsp+0x30], rbp
       mov      r14d, 3
       jmp      G_M000_IG16
 
G_M000_IG06:                ;; offset=0x006A
       mov      r14d, dword ptr [rbx+0x04]
       mov      eax, dword ptr [rsi+0x04]
       imul     r14, rax
       mul      rdx:rax, qword ptr [rbx+0x08]
       add      r14, rdx
       add      rbp, rax
       cmp      rbp, rax
       jae      SHORT G_M000_IG08
 
G_M000_IG07:                ;; offset=0x0084
       mov      rcx, 0x7FFF3EA93098
       call     CORINFO_HELP_COUNTPROFILE32
       inc      r14
 
G_M000_IG08:                ;; offset=0x0096
       mov      rax, qword ptr [rsi+0x08]
       mov      edx, dword ptr [rbx+0x04]
       mul      rdx:rax, rdx
       add      r14, rdx
       add      rbp, rax
       cmp      rbp, rax
       jae      SHORT G_M000_IG10
 
G_M000_IG09:                ;; offset=0x00AB
       mov      rcx, 0x7FFF3EA9309C
       call     CORINFO_HELP_COUNTPROFILE32
       inc      r14
 
G_M000_IG10:                ;; offset=0x00BD
       mov      rcx, 0x7FFF3EA930A0
       call     CORINFO_HELP_COUNTPROFILE32
       mov      qword ptr [rsp+0x30], rbp
       mov      qword ptr [rsp+0x38], r14
       mov      r14d, 5
       jmp      SHORT G_M000_IG16
 
G_M000_IG11:                ;; offset=0x00DE
       mov      rax, qword ptr [rbx+0x08]
       mov      edx, dword ptr [rsi+0x08]
       mul      rdx:rax, rdx
       mov      rbp, rdx
       mov      qword ptr [rsp+0x28], rax
       cmp      dword ptr [rbx+0x04], 0
       je       SHORT G_M000_IG14
 
G_M000_IG12:                ;; offset=0x00F6
       mov      ebp, dword ptr [rsi+0x08]
       mov      ecx, dword ptr [rbx+0x04]
       imul     rbp, rcx
       add      rbp, rdx
       mov      rcx, rbp
       shr      rcx, 32
       jne      G_M000_IG22
 
G_M000_IG13:                ;; offset=0x0110
       mov      rcx, 0x7FFF3EA93090
       call     CORINFO_HELP_COUNTPROFILE32
 
G_M000_IG14:                ;; offset=0x011F
       mov      rcx, 0x7FFF3EA93094
       call     CORINFO_HELP_COUNTPROFILE32
 
G_M000_IG15:                ;; offset=0x012E
       mov      dword ptr [rsp+0x30], ebp
       mov      r14d, 2
 
G_M000_IG16:                ;; offset=0x0138
       lea      rcx, [rsp+0x28]
       mov      eax, r14d
       cmp      dword ptr [rcx+4*rax], 0
       jne      SHORT G_M000_IG19
 
G_M000_IG17:                ;; offset=0x0146
       test     r14d, r14d
       je       G_M000_IG27
 
G_M000_IG18:                ;; offset=0x014F
       mov      rcx, 0x7FFF3EA930A8
       call     CORINFO_HELP_COUNTPROFILE32
       dec      r14d
       lea      rcx, [rsp+0x28]
       mov      eax, r14d
       cmp      dword ptr [rcx+4*rax], 0
       je       SHORT G_M000_IG17
 
G_M000_IG19:                ;; offset=0x016F
       cmp      r14d, 2
       ja       G_M000_IG32
 
G_M000_IG20:                ;; offset=0x0179
       cmp      edi, 28
       jle      G_M000_IG29
 
G_M000_IG21:                ;; offset=0x0182
       mov      rcx, 0x7FFF3EA930AC
       call     CORINFO_HELP_COUNTPROFILE32
       jmp      G_M000_IG32
 
G_M000_IG22:                ;; offset=0x0196
       mov      rcx, 0x7FFF3EA9308C
       call     CORINFO_HELP_COUNTPROFILE32
       jmp      G_M000_IG31
 
G_M000_IG23:                ;; offset=0x01AA
       mov      eax, dword ptr [rsi+0x04]
       or       eax, dword ptr [rsi+0x0C]
       je       G_M000_IG36
 
G_M000_IG24:                ;; offset=0x01B6
       mov      eax, dword ptr [rbx+0x08]
       mul      rdx:rax, qword ptr [rsi+0x08]
       mov      rbp, rdx
       mov      qword ptr [rsp+0x28], rax
       cmp      dword ptr [rsi+0x04], 0
       je       G_M000_IG15
 
G_M000_IG25:                ;; offset=0x01CF
       mov      ebp, dword ptr [rbx+0x08]
       mov      ecx, dword ptr [rsi+0x04]
       imul     rbp, rcx
       add      rbp, rdx
       mov      rcx, rbp
       shr      rcx, 32
       jne      SHORT G_M000_IG30
 
G_M000_IG26:                ;; offset=0x01E5
       mov      rcx, 0x7FFF3EA93088
       call     CORINFO_HELP_COUNTPROFILE32
       jmp      G_M000_IG15
 
G_M000_IG27:                ;; offset=0x01F9
       mov      rcx, 0x7FFF3EA930B8
       call     CORINFO_HELP_COUNTPROFILE32
 
G_M000_IG28:                ;; offset=0x0208
       mov      rcx, 0x7FFF3EA930BC
       call     CORINFO_HELP_COUNTPROFILE32
       vxorps   xmm0, xmm0, xmm0
       vmovups  xmmword ptr [rbx], xmm0
       jmp      SHORT G_M000_IG35
 
G_M000_IG29:                ;; offset=0x0221
       mov      rcx, 0x7FFF3EA930B4
       call     CORINFO_HELP_COUNTPROFILE32
       jmp      SHORT G_M000_IG33
 
G_M000_IG30:                ;; offset=0x0232
       mov      rcx, 0x7FFF3EA93084
       call     CORINFO_HELP_COUNTPROFILE32
 
G_M000_IG31:                ;; offset=0x0241
       mov      qword ptr [rsp+0x30], rbp
       mov      r14d, 3
 
G_M000_IG32:                ;; offset=0x024C
       lea      rcx, [rsp+0x28]
       mov      edx, r14d
       mov      r8d, edi
       call     [System.Decimal+DecCalc:ScaleResult(ptr,uint,int):int]
       mov      edi, eax
 
G_M000_IG33:                ;; offset=0x025F
       mov      rcx, 0x7FFF3EA930B0
       call     CORINFO_HELP_COUNTPROFILE32
       mov      rcx, qword ptr [rsp+0x28]
       mov      qword ptr [rbx+0x08], rcx
       mov      ecx, dword ptr [rsp+0x30]
       mov      dword ptr [rbx+0x04], ecx
 
G_M000_IG34:                ;; offset=0x027E
       mov      eax, dword ptr [rsi]
       xor      eax, dword ptr [rbx]
       and      eax, 0xFFFFFFFF80000000
       mov      ecx, edi
       shl      ecx, 16
       or       eax, ecx
       mov      dword ptr [rbx], eax
 
G_M000_IG35:                ;; offset=0x0290
       add      rsp, 64
       pop      rbx
       pop      rbp
       pop      rsi
       pop      rdi
       pop      r14
       ret      
 
G_M000_IG36:                ;; offset=0x029B
       mov      ebp, dword ptr [rbx+0x08]
       mov      r14d, dword ptr [rsi+0x08]
       imul     rbp, r14
       cmp      edi, 28
       jle      SHORT G_M000_IG43
 
G_M000_IG37:                ;; offset=0x02AB
       cmp      edi, 47
       jg       G_M000_IG28
 
G_M000_IG38:                ;; offset=0x02B4
       add      edi, -29
       mov      eax, edi
       mov      rdx, 0x7FFF70BBB528
       mov      rcx, qword ptr [rdx+8*rax]
       mov      rax, rbp
       xor      edx, edx
       div      rdx:rax, rcx
       mov      rdi, rax
       imul     rax, rcx
       sub      rbp, rax
       mov      r14, rdi
       shr      rcx, 1
       cmp      rbp, rcx
       jb       SHORT G_M000_IG42
 
G_M000_IG39:                ;; offset=0x02E4
       cmp      rbp, rcx
       ja       SHORT G_M000_IG41
 
G_M000_IG40:                ;; offset=0x02E9
       test     dil, 1
       je       SHORT G_M000_IG45
       jmp      SHORT G_M000_IG44
 
G_M000_IG41:                ;; offset=0x02F1
       mov      rcx, 0x7FFF3EA93074
       call     CORINFO_HELP_COUNTPROFILE32
       lea      r14, [rdi+0x01]
 
G_M000_IG42:                ;; offset=0x0304
       mov      rcx, 0x7FFF3EA93078
       call     CORINFO_HELP_COUNTPROFILE32
       mov      edi, 28
       mov      rbp, r14
 
G_M000_IG43:                ;; offset=0x031B
       mov      rcx, 0x7FFF3EA9307C
       call     CORINFO_HELP_COUNTPROFILE32
       mov      qword ptr [rbx+0x08], rbp
       jmp      G_M000_IG34
 
G_M000_IG44:                ;; offset=0x0333
       mov      rcx, 0x7FFF3EA93070
       call     CORINFO_HELP_COUNTPROFILE32
       jmp      SHORT G_M000_IG41
 
G_M000_IG45:                ;; offset=0x0344
       mov      rcx, 0x7FFF3EA93080
       call     CORINFO_HELP_COUNTPROFILE32
       jmp      SHORT G_M000_IG42
 
; Total bytes of code 853

