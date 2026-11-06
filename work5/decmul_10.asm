; Assembly listing for method System.Decimal+DecCalc:VarDecMul(byref,byref) (Instrumented Tier1)
; Emitting BLENDED_CODE for generic X64 + VEX on Windows
; Instrumented Tier1 code
; optimized code
; optimized using Synthesized PGO
; rsp based frame
; fully interruptible
; with Synthesized PGO: fgCalledCount is 100
; No PGO data
; 0 inlinees with PGO data; 52 single block inlinees; 5 inlinees without PGO data

G_M000_IG01:                ;; offset=0x0000
       push     r15
       push     r14
       push     rdi
       push     rsi
       push     rbp
       push     rbx
       sub      rsp, 104
       mov      rbx, rcx
       mov      rsi, rdx
 
G_M000_IG02:                ;; offset=0x0012
       mov      eax, dword ptr [rbx]
       add      eax, dword ptr [rsi]
       shr      eax, 16
       movzx    rdi, al
       mov      eax, dword ptr [rbx+0x04]
       or       eax, dword ptr [rbx+0x0C]
       jne      G_M000_IG18
 
G_M000_IG03:                ;; offset=0x0029
       mov      eax, dword ptr [rsi+0x04]
       or       eax, dword ptr [rsi+0x0C]
       jne      G_M000_IG14
 
G_M000_IG04:                ;; offset=0x0035
       mov      ebp, dword ptr [rbx+0x08]
       mov      r14d, dword ptr [rsi+0x08]
       imul     rbp, r14
       cmp      edi, 28
       jle      G_M000_IG12
 
G_M000_IG05:                ;; offset=0x0049
       cmp      edi, 47
       jg       G_M000_IG44
 
G_M000_IG06:                ;; offset=0x0052
       add      edi, -29
       mov      eax, edi
       mov      rdx, 0x7FFFA0009540
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
       jb       SHORT G_M000_IG11
 
G_M000_IG07:                ;; offset=0x0082
       cmp      rbp, rcx
       ja       SHORT G_M000_IG10
 
G_M000_IG08:                ;; offset=0x0087
       test     dil, 1
       je       SHORT G_M000_IG13
 
G_M000_IG09:                ;; offset=0x008D
       mov      rcx, 0x7FFF4147FB00
       call     CORINFO_HELP_COUNTPROFILE32
 
G_M000_IG10:                ;; offset=0x009C
       mov      rcx, 0x7FFF4147FB04
       call     CORINFO_HELP_COUNTPROFILE32
       lea      r14, [rdi+0x01]
 
G_M000_IG11:                ;; offset=0x00AF
       mov      rcx, 0x7FFF4147FB08
       call     CORINFO_HELP_COUNTPROFILE32
       mov      edi, 28
       mov      rbp, r14
 
G_M000_IG12:                ;; offset=0x00C6
       mov      rcx, 0x7FFF4147FB0C
       call     CORINFO_HELP_COUNTPROFILE32
       mov      qword ptr [rbx+0x08], rbp
       jmp      G_M000_IG25
 
G_M000_IG13:                ;; offset=0x00DE
       mov      rcx, 0x7FFF4147FB10
       call     CORINFO_HELP_COUNTPROFILE32
       jmp      SHORT G_M000_IG11
 
G_M000_IG14:                ;; offset=0x00EF
       mov      rdx, qword ptr [rsi+0x08]
       mov      ecx, dword ptr [rbx+0x08]
       lea      rax, [rsp+0x48]
       mulx     rbp, r8, rcx
       mov      qword ptr [rax], r8
       mov      rcx, qword ptr [rsp+0x48]
       mov      r14, rbp
       mov      qword ptr [rsp+0x50], rcx
       cmp      dword ptr [rsi+0x04], 0
       je       G_M000_IG29
 
G_M000_IG15:                ;; offset=0x011A
       mov      r14d, dword ptr [rbx+0x08]
       mov      ecx, dword ptr [rsi+0x04]
       imul     r14, rcx
       add      r14, rbp
       mov      rcx, r14
       shr      rcx, 32
       je       SHORT G_M000_IG17
 
G_M000_IG16:                ;; offset=0x0131
       mov      rcx, 0x7FFF4147FB14
       call     CORINFO_HELP_COUNTPROFILE32
       jmp      SHORT G_M000_IG22
 
G_M000_IG17:                ;; offset=0x0142
       mov      rcx, 0x7FFF4147FB18
       call     CORINFO_HELP_COUNTPROFILE32
       jmp      G_M000_IG29
 
G_M000_IG18:                ;; offset=0x0156
       mov      edx, dword ptr [rsi+0x04]
       or       edx, dword ptr [rsi+0x0C]
       jne      G_M000_IG36
 
G_M000_IG19:                ;; offset=0x0162
       mov      rdx, qword ptr [rbx+0x08]
       mov      ecx, dword ptr [rsi+0x08]
       lea      rax, [rsp+0x40]
       mulx     r14, r8, rcx
       mov      qword ptr [rax], r8
       mov      rcx, qword ptr [rsp+0x40]
       mov      rbp, r14
       mov      qword ptr [rsp+0x50], rcx
       cmp      dword ptr [rbx+0x04], 0
       je       G_M000_IG28
 
G_M000_IG20:                ;; offset=0x018D
       mov      ebp, dword ptr [rsi+0x08]
       mov      ecx, dword ptr [rbx+0x04]
       imul     rbp, rcx
       add      rbp, r14
       mov      rcx, rbp
       shr      rcx, 32
       je       SHORT G_M000_IG27
 
G_M000_IG21:                ;; offset=0x01A3
       mov      rcx, 0x7FFF4147FB1C
       call     CORINFO_HELP_COUNTPROFILE32
       mov      r14, rbp
 
G_M000_IG22:                ;; offset=0x01B5
       mov      qword ptr [rsp+0x58], r14
       mov      ebp, 3
 
G_M000_IG23:                ;; offset=0x01BF
       lea      rcx, [rsp+0x50]
       mov      edx, ebp
       mov      r8d, edi
       call     [System.Decimal+DecCalc:ScaleResult(ptr,uint,int):int]
       mov      edi, eax
 
G_M000_IG24:                ;; offset=0x01D1
       mov      rcx, 0x7FFF4147FB40
       call     CORINFO_HELP_COUNTPROFILE32
       mov      rax, qword ptr [rsp+0x50]
       mov      qword ptr [rbx+0x08], rax
       mov      eax, dword ptr [rsp+0x58]
       mov      dword ptr [rbx+0x04], eax
 
G_M000_IG25:                ;; offset=0x01F0
       mov      eax, dword ptr [rsi]
       xor      eax, dword ptr [rbx]
       and      eax, 0xFFFFFFFF80000000
       mov      ecx, edi
       shl      ecx, 16
       or       eax, ecx
       mov      dword ptr [rbx], eax
 
G_M000_IG26:                ;; offset=0x0202
       add      rsp, 104
       pop      rbx
       pop      rbp
       pop      rsi
       pop      rdi
       pop      r14
       pop      r15
       ret      
 
G_M000_IG27:                ;; offset=0x020F
       mov      rcx, 0x7FFF4147FB20
       call     CORINFO_HELP_COUNTPROFILE32
 
G_M000_IG28:                ;; offset=0x021E
       mov      rcx, 0x7FFF4147FB24
       call     CORINFO_HELP_COUNTPROFILE32
       mov      r14, rbp
 
G_M000_IG29:                ;; offset=0x0230
       mov      dword ptr [rsp+0x58], r14d
       mov      ebp, 2
 
G_M000_IG30:                ;; offset=0x023A
       lea      rcx, [rsp+0x50]
       mov      eax, ebp
       cmp      dword ptr [rcx+4*rax], 0
       jne      SHORT G_M000_IG33
 
G_M000_IG31:                ;; offset=0x0247
       test     ebp, ebp
       je       G_M000_IG43
 
G_M000_IG32:                ;; offset=0x024F
       mov      rcx, 0x7FFF4147FB38
       call     CORINFO_HELP_COUNTPROFILE32
       dec      ebp
       lea      rcx, [rsp+0x50]
       mov      eax, ebp
       cmp      dword ptr [rcx+4*rax], 0
       je       SHORT G_M000_IG31
 
G_M000_IG33:                ;; offset=0x026D
       cmp      ebp, 2
       ja       G_M000_IG23
 
G_M000_IG34:                ;; offset=0x0276
       cmp      edi, 28
       jle      G_M000_IG45
 
G_M000_IG35:                ;; offset=0x027F
       mov      rcx, 0x7FFF4147FB3C
       call     CORINFO_HELP_COUNTPROFILE32
       jmp      G_M000_IG23
 
G_M000_IG36:                ;; offset=0x0293
       mov      rdx, qword ptr [rbx+0x08]
       mov      rcx, qword ptr [rsi+0x08]
       lea      rax, [rsp+0x38]
       mulx     r15, r8, rcx
       mov      qword ptr [rax], r8
       mov      r14, qword ptr [rsp+0x38]
       mov      qword ptr [rsp+0x50], r14
       mov      edx, dword ptr [rbx+0x04]
       or       edx, dword ptr [rsi+0x04]
       je       G_M000_IG42
 
G_M000_IG37:                ;; offset=0x02BE
       mov      ebp, dword ptr [rbx+0x04]
       mov      ecx, dword ptr [rsi+0x04]
       imul     rbp, rcx
       mov      rdx, qword ptr [rbx+0x08]
       lea      rax, [rsp+0x30]
       mulx     rcx, r8, rcx
       mov      qword ptr [rax], r8
       mov      r14, qword ptr [rsp+0x30]
       add      rbp, rcx
       add      r15, r14
       cmp      r15, r14
       jae      SHORT G_M000_IG39
 
G_M000_IG38:                ;; offset=0x02E9
       mov      rcx, 0x7FFF4147FB28
       call     CORINFO_HELP_COUNTPROFILE32
       inc      rbp
 
G_M000_IG39:                ;; offset=0x02FB
       mov      rdx, qword ptr [rsi+0x08]
       mov      ecx, dword ptr [rbx+0x04]
       lea      rax, [rsp+0x28]
       mulx     rcx, r8, rcx
       mov      qword ptr [rax], r8
       mov      r14, qword ptr [rsp+0x28]
       add      rbp, rcx
       add      r15, r14
       cmp      r15, r14
       jae      SHORT G_M000_IG41
 
G_M000_IG40:                ;; offset=0x031F
       mov      rcx, 0x7FFF4147FB2C
       call     CORINFO_HELP_COUNTPROFILE32
       inc      rbp
 
G_M000_IG41:                ;; offset=0x0331
       mov      rcx, 0x7FFF4147FB30
       call     CORINFO_HELP_COUNTPROFILE32
       mov      qword ptr [rsp+0x58], r15
       mov      qword ptr [rsp+0x60], rbp
       mov      ebp, 5
       jmp      G_M000_IG30
 
G_M000_IG42:                ;; offset=0x0354
       mov      rcx, 0x7FFF4147FB34
       call     CORINFO_HELP_COUNTPROFILE32
       mov      qword ptr [rsp+0x58], r15
       mov      ebp, 3
       jmp      G_M000_IG30
 
G_M000_IG43:                ;; offset=0x0372
       mov      rcx, 0x7FFF4147FB48
       call     CORINFO_HELP_COUNTPROFILE32
 
G_M000_IG44:                ;; offset=0x0381
       mov      rcx, 0x7FFF4147FB4C
       call     CORINFO_HELP_COUNTPROFILE32
       vxorps   xmm0, xmm0, xmm0
       vmovups  xmmword ptr [rbx], xmm0
       jmp      G_M000_IG26
 
G_M000_IG45:                ;; offset=0x039D
       mov      rcx, 0x7FFF4147FB44
       call     CORINFO_HELP_COUNTPROFILE32
       jmp      G_M000_IG24
 
; Total bytes of code 945

